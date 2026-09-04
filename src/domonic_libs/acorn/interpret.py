"""A tree-walking evaluator for the ESTree the parser produces -- enough of
ECMAScript to run DOM-manipulation scripts against domonic's ``document`` /
``window`` / ``console`` and the ``domonic.javascript`` globals.

    from domonic_libs.acorn.interpret import run_js
    run_js("const b = document.createElement('button'); b.textContent = 'Go';"
           "document.body.appendChild(b);")

Covers the practical language: expressions, statements, closures, ``class``
(extends / super / fields / getters-setters / private / static), destructuring,
generators (thread-backed), ES modules, labelled break/continue, a pragmatic
event loop (``Promise`` / ``async`` / ``await`` / ``setTimeout``), and the
``Array`` / ``String`` / ``Object`` / ``Number`` / ``Math`` / ``JSON`` /
``RegExp`` built-ins (delegating to ``domonic.javascript`` where it is
spec-solid). It passes a curated test262-style battery
(``python -m domonic_libs.js262``). Not covered -- real prototype chains,
``Proxy`` / ``Symbol``, ``with``. ``async`` functions run to completion eagerly
(``await`` pumps the loop inline) rather than suspending at the first ``await``.
It runs against a *live* domonic DOM, so a script that appends an element mutates
the Python tree.
"""

from __future__ import annotations

import collections
import heapq
import importlib
import math
import os
import queue
import re
import threading
import time

from .parser import Parser

# ``import``/``export`` at the start of a line -> parse as an ES module.
_MODULE_HINT = re.compile(r"^\s*(?:export\b|import\s+(?:[\"']|[\w{*]))", re.M)

# -- sentinels & control-flow signals -------------------------------------


class _Undefined:
    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self):
        return "undefined"

    def __bool__(self):
        return False


UNDEFINED = _Undefined()


class _Return(Exception):
    def __init__(self, value):
        self.value = value


class _Break(Exception):
    def __init__(self, label=None):
        self.label = label


class _Continue(Exception):
    def __init__(self, label=None):
        self.label = label


class JSThrow(Exception):
    def __init__(self, value):
        self.value = value
        super().__init__(_stringify(value))


class JSSyntaxError(SyntaxError):
    pass


# -- event loop ------------------------------------------------------------

class EventLoop:
    """A small synchronous event loop: a microtask queue, timer heap, and a
    counter of in-flight background I/O (threads that will post a microtask when
    they finish). ``await`` and end-of-script both drain it via :meth:`run` /
    :meth:`run_until`."""

    def __init__(self):
        self._micro = collections.deque()
        self._timers = []          # heap of [due, ord, tid, cb, interval_ms|None]
        self._ord = 0              # tie-breaker for the heap
        self._next_tid = 0
        self._live = set()         # tids of active timers / intervals
        self._pending_io = 0

    # -- scheduling
    def micro(self, cb):
        self._micro.append(cb)

    def timer(self, cb, ms, interval=False, _tid=None):
        if _tid is None:
            self._next_tid += 1
            _tid = self._next_tid
        self._live.add(_tid)
        self._ord += 1
        heapq.heappush(self._timers, [time.monotonic() + max(0.0, ms) / 1000.0,
                                      self._ord, _tid, cb, (ms if interval else None)])
        return _tid

    def clear(self, tid):
        self._live.discard(tid)

    def io_start(self):
        self._pending_io += 1

    def io_finish(self, cb=None):
        self._pending_io -= 1
        if cb is not None:
            self._micro.append(cb)

    def post(self, cb):
        """Thread-safe: enqueue a microtask from a background thread."""
        self._micro.append(cb)

    # -- draining
    def _has_work(self):
        return bool(self._micro) or any(e[2] in self._live for e in self._timers) or self._pending_io > 0

    def _drain_micro(self):
        ran = False
        while self._micro:
            self._micro.popleft()()
            ran = True
        return ran

    def _step(self):
        if self._drain_micro():
            return True
        while self._timers and self._timers[0][2] not in self._live:
            heapq.heappop(self._timers)        # drop cancelled timers
        if self._timers:
            due, _ord, tid, cb, interval = self._timers[0]
            delay = due - time.monotonic()
            if delay > 0:
                time.sleep(min(delay, 0.05))
            if time.monotonic() >= due:
                heapq.heappop(self._timers)
                if tid in self._live:
                    if interval is None:
                        self._live.discard(tid)
                    else:
                        self.timer(cb, interval, interval=True, _tid=tid)
                    cb()
            return True
        if self._pending_io > 0:
            time.sleep(0.005)
            return True
        return False

    def run(self):
        while self._has_work():
            if not self._step():
                break

    def run_until(self, done):
        while not done():
            if not self._has_work():
                raise JSThrow(_make_error(
                    "Error", "await on a promise that will never settle (no event-loop work left)"))
            self._step()


class _Promise:
    __slots__ = ("loop", "state", "value", "_cbs")

    def __init__(self, loop):
        self.loop = loop
        self.state = "pending"
        self.value = UNDEFINED
        self._cbs = []

    # -- settling
    def _resolve(self, value=UNDEFINED, *_):
        if self.state != "pending":
            return
        if isinstance(value, _Promise):
            value._on(self._resolve, self._reject)
            return
        if isinstance(value, dict) and callable(value.get("then")):  # thenable
            try:
                value["then"](self._resolve, self._reject)
            except JSThrow as e:
                self._reject(e.value)
            return
        self.state = "fulfilled"
        self.value = value
        self._flush()

    def _reject(self, reason=UNDEFINED, *_):
        if self.state != "pending":
            return
        self.state = "rejected"
        self.value = reason
        self._flush()

    def _flush(self):
        cbs, self._cbs = self._cbs, []
        for entry in cbs:
            self.loop.micro(lambda e=entry: self._dispatch(*e))

    def _dispatch(self, on_ful, on_rej, nxt):
        handler = on_ful if self.state == "fulfilled" else on_rej
        if handler is None or not callable(handler):
            (nxt._resolve if self.state == "fulfilled" else nxt._reject)(self.value)
            return
        try:
            nxt._resolve(handler(self.value))
        except JSThrow as e:
            nxt._reject(e.value)

    def _on(self, on_ful, on_rej):
        nxt = _Promise(self.loop)
        if self.state == "pending":
            self._cbs.append((on_ful, on_rej, nxt))
        else:
            self.loop.micro(lambda: self._dispatch(on_ful, on_rej, nxt))
        return nxt

    # -- JS surface
    def then(self, on_ful=None, on_rej=None):
        return self._on(on_ful if callable(on_ful) else None,
                        on_rej if callable(on_rej) else None)

    def catch(self, on_rej=None):
        return self._on(None, on_rej if callable(on_rej) else None)

    def finally_(self, cb=None):
        def wrap_ful(v):
            if callable(cb):
                cb()
            return v

        def wrap_rej(e):
            if callable(cb):
                cb()
            raise JSThrow(e)
        return self._on(wrap_ful, wrap_rej)

    def __getattr__(self, name):
        if name == "finally":
            return self.finally_
        raise AttributeError(name)

    def __repr__(self):
        return f"Promise {{ <{self.state}> }}"


def _make_promise_api(loop):
    def ctor(executor=None, *_a, _this=UNDEFINED, _new=False):
        p = _Promise(loop)
        if callable(executor):
            try:
                executor(p._resolve, p._reject)
            except JSThrow as e:
                p._reject(e.value)
        return p

    def resolved(v=UNDEFINED, *_):
        p = _Promise(loop)
        p._resolve(v)
        return p

    def rejected(e=UNDEFINED, *_):
        p = _Promise(loop)
        p._reject(e)
        return p

    def all_(items, *_):
        items = list(items)
        out = _Promise(loop)
        results = [UNDEFINED] * len(items)
        left = [len(items)]
        if not items:
            out._resolve(JSArray())
        for i, it in enumerate(items):
            pr = it if isinstance(it, _Promise) else resolved(it)

            def ok(v, i=i):
                results[i] = v
                left[0] -= 1
                if left[0] == 0:
                    out._resolve(JSArray(results))
            pr._on(ok, out._reject)
        return out

    def all_settled(items, *_):
        items = list(items)
        out = _Promise(loop)
        results = [UNDEFINED] * len(items)
        left = [len(items)]
        if not items:
            out._resolve(JSArray())
        for i, it in enumerate(items):
            pr = it if isinstance(it, _Promise) else resolved(it)

            def done(status, key):
                def cb(v, i=i, status=status, key=key):
                    results[i] = JSObject({"status": status, key: v})
                    left[0] -= 1
                    if left[0] == 0:
                        out._resolve(JSArray(results))
                return cb
            pr._on(done("fulfilled", "value"), done("rejected", "reason"))
        return out

    def race(items, *_):
        out = _Promise(loop)
        for it in items:
            pr = it if isinstance(it, _Promise) else resolved(it)
            pr._on(out._resolve, out._reject)
        return out

    def any_(items, *_):
        items = list(items)
        out = _Promise(loop)
        left = [len(items)]
        errors = [UNDEFINED] * len(items)
        for i, it in enumerate(items):
            pr = it if isinstance(it, _Promise) else resolved(it)

            def bad(e, i=i):
                errors[i] = e
                left[0] -= 1
                if left[0] == 0:
                    out._reject(_make_error("AggregateError", "All promises were rejected"))
            pr._on(out._resolve, bad)
        return out

    ctor.resolve = resolved
    ctor.reject = rejected
    ctor.all = all_
    ctor.allSettled = all_settled
    ctor.race = race
    ctor.any = any_
    return ctor


# -- runtime object types ----------------------------------------------


class JSObject(dict):
    """A plain JS object. Attribute access mirrors item access."""

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)  # let Python protocols (copy, pickle) work
        try:
            return self[name]
        except KeyError:
            return UNDEFINED

    def __setattr__(self, name, value):
        self[name] = value

    def __repr__(self):
        return "{" + ", ".join(f"{k}: {_stringify(v)}" for k, v in self.items()) + "}"


class JSArray(list):
    @property
    def length(self):
        return len(self)


def _intern(obj, name):
    """Read an interpreter-internal attribute (``_accessors`` / ``_frozen``)
    without tripping ``JSObject.__getattr__``, which returns ``UNDEFINED`` for
    missing keys rather than raising."""
    d = getattr(obj, "__dict__", None)
    return d.get(name) if d is not None else None


class Environment:
    __slots__ = ("vars", "parent", "this", "glob", "consts")

    def __init__(self, parent=None, this=UNDEFINED):
        self.vars = {}
        self.parent = parent
        self.this = this if this is not UNDEFINED or parent is None else parent.this
        self.glob = None  # only the root env carries the global object
        self.consts = None  # set of names declared `const` in this scope

    def declare(self, name, value, const=False):
        self.vars[name] = value
        if const:
            if self.consts is None:
                self.consts = set()
            self.consts.add(name)

    def get(self, name):
        env = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            last = env
            env = env.parent
        if last.glob is not None:
            v = js_get_safe(last.glob, name)
            if v is not UNDEFINED:
                return v
        raise JSThrow(_make_error("ReferenceError", f"{name} is not defined"))

    def set(self, name, value):
        env = self
        while env is not None:
            if name in env.vars:
                if env.consts is not None and name in env.consts:
                    raise JSThrow(_make_error("TypeError", "Assignment to constant variable."))
                env.vars[name] = value
                return
            root = env
            env = env.parent
        root.vars[name] = value  # implicit global (sloppy mode)

    def has(self, name):
        env = self
        while env is not None:
            if name in env.vars:
                return True
            last = env
            env = env.parent
        return last.glob is not None and js_get_safe(last.glob, name) is not UNDEFINED


def js_get_safe(obj, key):
    try:
        return js_get(obj, key)
    except Exception:
        return UNDEFINED


class JSFunction:
    def __init__(self, node, closure, interp, is_arrow=False, name=None):
        self.node = node
        self.closure = closure
        self.interp = interp
        self.is_arrow = is_arrow
        self.name = name or (node.id.name if getattr(node, "id", None) else "")
        self.prototype = JSObject()

    def __call__(self, *args, _this=UNDEFINED, _new=False):
        if getattr(self.node, "generator", False):
            return JSGenerator(self, args, _this)
        if getattr(self.node, "async", False):
            return self._call_async(args, _this)
        return self._call_sync(args, _this)

    def _call_sync(self, args, _this):
        env = Environment(self.closure, this=(self.closure.this if self.is_arrow else _this))
        params = self.node.params
        env.declare("arguments", JSArray(args))
        self.interp._bind_params(params, list(args), env)
        body = self.node.body
        self.interp.frames.append(self.name or ("<anonymous>" if not self.is_arrow else "<arrow>"))
        try:
            if getattr(body, "type", None) != "BlockStatement":
                return self.interp.evaluate(body, env)  # expression-bodied arrow
            try:
                self.interp._exec_block(body.body, env, hoist=True)
            except _Return as r:
                return r.value
            return UNDEFINED
        except (JSThrow, JSSyntaxError) as err:
            self.interp._attach_trace(err)
            raise
        finally:
            self.interp.frames.pop()

    def _call_async(self, args, _this):
        """``async`` functions run to completion synchronously (``await`` pumps
        the loop inline) and hand back a settled promise."""
        p = _Promise(self.interp.loop)
        try:
            p._resolve(self._call_sync(args, _this))
        except JSThrow as err:
            p._reject(err.value)
        return p

    def __repr__(self):
        return f"function {self.name}() {{ … }}"


_GEN_STOP = object()


class _GenReturn(Exception):
    def __init__(self, value):
        self.value = value


class JSGenerator:
    """A generator object, driven by a paused worker thread. Only one of the
    caller / the generator body runs at a time (strict ping-pong over two
    queues), so the interpreter's shared state stays consistent."""

    def __init__(self, fn, args, this):
        self.interp = fn.interp
        self._resume = queue.Queue(1)   # value sent in via next(v) / _GEN_STOP
        self._out = queue.Queue(1)      # ("yield"|"return"|"throw", payload)
        self._done = False
        self._started = False

        def run():
            self._resume.get()  # wait for the first next()
            env = Environment(fn.closure, this=(fn.closure.this if fn.is_arrow else this))
            env.declare("arguments", JSArray(args))
            self.interp._bind_params(fn.node.params, list(args), env)
            try:
                self.interp._exec_block(fn.node.body.body, env, hoist=True)
                self._out.put(("return", UNDEFINED))
            except _Return as r:
                self._out.put(("return", r.value))
            except _GenReturn as r:
                self._out.put(("return", r.value))
            except JSThrow as e:
                self._out.put(("throw", e))
            except BaseException as e:  # noqa: BLE001
                self._out.put(("throw", JSThrow(_make_error("Error", str(e)))))

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    # -- called from _ex_YieldExpression, on the worker thread
    def _do_yield(self, value):
        self._out.put(("yield", value))
        sent = self._resume.get()
        if sent is _GEN_STOP:
            raise _GenReturn(UNDEFINED)
        return sent

    # -- JS surface, on the caller thread
    def _pump(self, sent):
        if self._done:
            return JSObject({"value": UNDEFINED, "done": True})
        prev = self.interp._current_gen
        self.interp._current_gen = self
        self._resume.put(sent)
        kind, payload = self._out.get()
        self.interp._current_gen = prev
        if kind == "yield":
            return JSObject({"value": payload, "done": False})
        self._done = True
        if kind == "throw":
            raise payload
        return JSObject({"value": payload, "done": True})

    def next(self, value=UNDEFINED, *_):
        return self._pump(value)

    def send(self, value=UNDEFINED, *_):
        return self._pump(value)

    def _return(self, value=UNDEFINED, *_):
        if not self._done:
            self._resume.put(_GEN_STOP)
            self._out.get()
            self._done = True
        return JSObject({"value": value, "done": True})

    def throw(self, err=UNDEFINED, *_):
        # simplest useful behaviour: finish the generator, propagate
        self._return()
        raise JSThrow(err)

    def __getattr__(self, name):
        if name == "return":
            return self._return
        raise AttributeError(name)

    def __iter__(self):
        while True:
            r = self._pump(UNDEFINED)
            if r["done"]:
                return
            yield r["value"]

    def __repr__(self):
        return "[object Generator]"


class _Accessor:
    __slots__ = ("get", "set")

    def __init__(self, get=None, set=None):
        self.get = get
        self.set = set


class JSClass:
    def __init__(self, name, ctor, methods, statics, superclass, interp, fields=None, accessors=None):
        self.name = name
        self.ctor = ctor
        self.methods = methods          # name -> JSFunction
        self.statics = statics          # name -> value
        self.superclass = superclass
        self.interp = interp
        self.fields = fields or []       # [(name, value_node, field_env)]
        self.accessors = accessors or {}  # name -> _Accessor

    def __getattr__(self, name):
        st = object.__getattribute__(self, "statics")
        if name in st:
            return st[name]
        raise AttributeError(name)

    def __call__(self, *args, _this=UNDEFINED, _new=False):
        inst = _this if isinstance(_this, JSInstance) else JSInstance(self)
        # run field initialisers + constructor up the chain
        self._construct(inst, args)
        return inst

    def _construct(self, inst, args):
        self.interp.frames.append("new " + (self.name or "<anonymous>"))
        try:
            for name, node, fenv in self.fields:
                fe = Environment(fenv, this=inst)
                inst[name] = self.interp.evaluate(node, fe) if node is not None else UNDEFINED
            if self.ctor:
                self.ctor.__call__(*args, _this=inst)
            elif self.superclass:
                self.superclass._construct(inst, args)
        except (JSThrow, JSSyntaxError) as err:
            self.interp._attach_trace(err)
            raise
        finally:
            self.interp.frames.pop()

    def method(self, name):
        cls = self
        while cls is not None:
            if name in cls.methods:
                return cls.methods[name]
            cls = cls.superclass
        return None

    def accessor(self, name):
        cls = self
        while cls is not None:
            if name in cls.accessors:
                return cls.accessors[name]
            cls = cls.superclass
        return None


class JSInstance(JSObject):
    def __init__(self, cls):
        super().__init__()
        object.__setattr__(self, "_cls", cls)

    def __getattr__(self, name):
        if name in self:
            return self[name]
        m = object.__getattribute__(self, "_cls").method(name)
        if m is not None:
            return _bound(m, self)
        return UNDEFINED


def _bound(fn, this):
    def call(*args, _this=UNDEFINED, _new=False):
        return fn.__call__(*args, _this=this)
    call.__wrapped_js__ = fn
    return call


# -- coercion helpers (the JS operator semantics) ----------------------


def _is_nan(v):
    return isinstance(v, float) and v != v


def js_truthy(v):
    if v is UNDEFINED or v is None or v is False:
        return False
    if v == 0 and isinstance(v, (int, float)) and not isinstance(v, bool):
        return not _is_nan(v) and False if v == 0 else True
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0 and not _is_nan(v)
    if isinstance(v, str):
        return len(v) > 0
    return True


def js_number(v):
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    if v is None:
        return 0
    if v is UNDEFINED:
        return float("nan")
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return 0
        try:
            if s.lower().startswith("0x"):
                return int(s, 16)
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return float("nan")
    if isinstance(v, (list, JSArray)):
        if len(v) == 0:
            return 0
        if len(v) == 1:
            return js_number(v[0])
    return float("nan")


def _stringify(v):
    if v is UNDEFINED:
        return "undefined"
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, float) and not isinstance(v, bool):
        return _num_to_str(v)
    if isinstance(v, int):
        return _num_to_str(v)
    if type(v) in (list, JSArray):
        return ",".join("" if x is None or x is UNDEFINED else _stringify(x) for x in v)
    if isinstance(v, (list, JSArray)):
        # a domonic list-like (DOMTokenList, ...) with its own stringifier
        s = str(v)
        return s if s != object.__repr__(v) else ",".join(_stringify(x) for x in v)
    if isinstance(v, str):
        return v
    if isinstance(v, JSInstance):
        m = v._cls.method("toString")
        if m is not None:
            r = m.__call__(_this=v)
            if isinstance(r, str):
                return r
        return "[object Object]"
    if isinstance(v, dict):
        own = dict.get(v, "toString")   # own property only -- avoid js_get recursion
        if callable(own):
            try:
                r = _invoke_any(own, [], v)
                if isinstance(r, str):
                    return r
            except Exception:
                pass
        return "[object Object]"
    if callable(v):
        return getattr(v, "__repr__", lambda: "function")()
    return str(v)


def _num_to_str(v):
    if isinstance(v, float):
        if v != v:
            return "NaN"
        if v == math.inf:
            return "Infinity"
        if v == -math.inf:
            return "-Infinity"
    if v == 0:
        return "0"
    av = abs(v)
    if av >= 1e21 or (av < 1e-6 and av > 0):
        s = repr(float(v))
        if "e" in s:            # Python "1e+21" -> JS "1e+21" (already close); normalise
            mant, exp = s.split("e")
            mant = mant.rstrip("0").rstrip(".") if "." in mant else mant
            sign = "+" if not exp.startswith("-") else "-"
            return f"{mant}e{sign}{int(exp.lstrip('+-'))}"
        return s
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, int):
        return str(v)
    return repr(v)


def js_add(a, b):
    if isinstance(a, str) or isinstance(b, str):
        return _stringify(a) + _stringify(b)
    if isinstance(a, (list, JSArray)) or isinstance(b, (list, JSArray)) or isinstance(a, dict) or isinstance(b, dict):
        return _stringify(a) + _stringify(b)
    return js_number(a) + js_number(b)


def js_loose_eq(a, b):
    if type(a) is type(b):
        return js_strict_eq(a, b)
    if (a is None or a is UNDEFINED) and (b is None or b is UNDEFINED):
        return True
    if a is None or a is UNDEFINED or b is None or b is UNDEFINED:
        return False
    if isinstance(a, bool):
        return js_loose_eq(js_number(a), b)
    if isinstance(b, bool):
        return js_loose_eq(a, js_number(b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return js_strict_eq(a, b)
    if isinstance(a, (int, float)) and isinstance(b, str):
        return js_strict_eq(a, js_number(b))
    if isinstance(a, str) and isinstance(b, (int, float)):
        return js_strict_eq(js_number(a), b)
    return a is b


def js_strict_eq(a, b):
    if _is_nan(a) or _is_nan(b):
        return False
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if type(a) is not type(b) and not (isinstance(a, str) and isinstance(b, str)):
        return a is b
    return a == b if isinstance(a, (str, int, float)) else a is b


def js_typeof(v):
    if v is UNDEFINED:
        return "undefined"
    if v is None:
        return "object"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if callable(v) or isinstance(v, (JSFunction, JSClass)):
        return "function"
    return "object"


def _to_key(v):
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return _stringify(v)
    return _stringify(v)


def _make_error(name, message):
    e = JSObject()
    e["name"] = name
    e["message"] = message
    e["stack"] = f"{name}: {message}"
    return e


# -- member get / set on any runtime value ----------------------------


def js_get(obj, key):
    key = _to_key(key)
    if obj is UNDEFINED or obj is None:
        raise JSThrow(_make_error("TypeError", f"Cannot read properties of {_stringify(obj)} (reading '{key}')"))
    if isinstance(obj, (bytes, bytearray)):
        if key == "length":
            return len(obj)
        try:
            return obj[int(key)]
        except (ValueError, TypeError, IndexError):
            return getattr(obj, key, UNDEFINED)
    if isinstance(obj, (str,)):
        if _has_astral(obj):
            u = _utf16(obj)          # JS strings are UTF-16 code-unit indexed
            if key == "length":
                return len(u)
            try:
                i = int(key)
                return u[i] if 0 <= i < len(u) else UNDEFINED
            except (ValueError, TypeError):
                pass
            d = _delegate_method("String", obj, key)  # domonic's String is UTF-16-aware
            if d is not UNDEFINED:
                return d
            return _str_method(obj, key)
        if key == "length":
            return len(obj)
        try:
            i = int(key)
            return obj[i] if 0 <= i < len(obj) else UNDEFINED
        except (ValueError, TypeError):
            pass
        return _str_method(obj, key)
    if isinstance(obj, (list, JSArray)):
        if key == "length":
            return len(obj)
        try:
            i = int(key)
            return obj[i] if 0 <= i < len(obj) else UNDEFINED
        except (ValueError, TypeError):
            pass
        # a domonic list-like (DOMTokenList, NodeList, HTMLCollection, ...) --
        # its own methods win over the generic Array delegation
        if type(obj) not in (list, JSArray):
            own = getattr(obj, key, UNDEFINED)
            if own is not UNDEFINED and own is not None:
                return own
        return _array_method(obj, key)
    if isinstance(obj, JSInstance):
        if key in obj:
            return obj[key]
        acc = obj._cls.accessor(key)
        if acc is not None and acc.get is not None:
            return acc.get.__call__(_this=obj)
        m = obj._cls.method(key)
        if m is not None:
            return _bound(m, obj)
        if key == "constructor":
            return obj._cls
        return _plain_object_method(obj, key)
    if isinstance(obj, JSClass):
        if key in obj.statics:
            return obj.statics[key]
        if key in obj.methods:
            return obj.methods[key]
        if key == "name":
            return obj.name
        return UNDEFINED
    if isinstance(obj, dict):
        acc = _intern(obj, "_accessors")
        if acc is not None and key in acc:
            g = acc[key].get
            return g.__call__(_this=obj) if g is not None else UNDEFINED
        if key in obj:
            return obj[key]
        # a dict *subclass* may carry real methods (host Response/ShellResult,
        # ...) -- plain dict / JSObject stay pure key stores
        if type(obj) not in (dict, JSObject):
            got = getattr(obj, key, UNDEFINED)
            if got is not UNDEFINED:
                return got
        return _plain_object_method(obj, key)
    if isinstance(obj, (int, float, bool)):
        return _number_method(obj, key)
    if type(obj).__name__ == "DOMStringMap":  # element.dataset -- JS proxy semantics
        try:
            return obj[key] if key in obj else UNDEFINED
        except TypeError:
            return UNDEFINED
    if isinstance(obj, JSFunction) or (callable(obj) and key in ("call", "apply", "bind")):
        fm = _fn_method(obj, key)
        if fm is not UNDEFINED:
            return fm
    # domonic element / JSFunction / arbitrary python object
    got = getattr(obj, key, UNDEFINED)
    if got is UNDEFINED and __import__("keyword").iskeyword(key):
        got = getattr(obj, key + "_", UNDEFINED)   # domonic uses from_/with_/... for keywords
    return got


def _fn_method(fn, key):
    if key == "call":
        return lambda this=UNDEFINED, *a: _invoke_any(fn, list(a), this)
    if key == "apply":
        return lambda this=UNDEFINED, arr=UNDEFINED, *_: _invoke_any(
            fn, list(arr) if isinstance(arr, (list, JSArray)) else [], this)
    if key == "bind":
        def bind(this=UNDEFINED, *bound):
            def bound_fn(*args, _this=UNDEFINED, _new=False):
                return _invoke_any(fn, list(bound) + list(args), this)
            bound_fn.__name__ = "bound " + getattr(fn, "name", "")
            return bound_fn
        return bind
    if isinstance(fn, JSFunction):
        if key == "name":
            return fn.name
        if key == "length":
            return sum(1 for p in fn.node.params if p.type == "Identifier")
        if key == "prototype":
            return fn.prototype
        if key in ("toString",):
            return lambda *_: repr(fn)
    return UNDEFINED


def _invoke_any(fn, args, this):
    if isinstance(fn, JSFunction):
        return fn.__call__(*args, _this=this)
    return fn(*args)


def _has_astral(s):
    return any(ord(c) > 0xFFFF for c in s)


def _utf16(s):
    """A string as a list of UTF-16 code units (astral chars -> surrogate pair)."""
    out = []
    for c in s:
        o = ord(c)
        if o > 0xFFFF:
            o -= 0x10000
            out.append(chr(0xD800 + (o >> 10)))
            out.append(chr(0xDC00 + (o & 0x3FF)))
        else:
            out.append(c)
    return out


def _plain_object_method(obj, key):
    """``Object.prototype`` methods available on any JS object / instance."""
    if key == "hasOwnProperty":
        return lambda k=UNDEFINED, *_: _to_key(k) in obj
    if key == "toString":
        return lambda *_: _stringify(obj)
    if key == "valueOf":
        return lambda *_: obj
    if key == "isPrototypeOf" or key == "propertyIsEnumerable":
        return lambda *_: False
    return UNDEFINED


def js_set(obj, key, value):
    key = _to_key(key)
    if isinstance(obj, JSInstance):
        acc = obj._cls.accessor(key)
        if acc is not None and acc.set is not None:
            acc.set.__call__(value, _this=obj)
            return value
        obj[key] = value
        return value
    if isinstance(obj, dict):
        acc = _intern(obj, "_accessors")
        if acc is not None and key in acc:
            s = acc[key].set
            if s is not None:
                s.__call__(value, _this=obj)
            return value
        if _intern(obj, "_frozen"):
            return value  # sloppy-mode: silently ignored
        obj[key] = value
        return value
    if type(obj).__name__ == "DOMStringMap":  # element.dataset write -> data-* attribute
        obj[key] = value
        return value
    if isinstance(obj, (list, JSArray)):
        if key == "length":
            n = int(js_number(value))
            del obj[n:]
            while len(obj) < n:
                obj.append(UNDEFINED)
            return value
        try:
            i = int(key)
            while len(obj) <= i:
                obj.append(UNDEFINED)
            obj[i] = value
            return value
        except (ValueError, TypeError):
            pass
    try:
        setattr(obj, key, value)
    except Exception:
        pass
    return value


_JS_TYPES = {}


def _js_type(name):
    if name not in _JS_TYPES:
        import domonic.javascript as _j
        _JS_TYPES[name] = getattr(_j, name)
    return _JS_TYPES[name]


def _unwrap_js(v):
    """domonic ``javascript.String`` / ``Number`` wrappers and plain lists ->
    the interpreter's own primitive representation."""
    if v is None:
        return UNDEFINED   # domonic uses None for "no result"; JS methods mean undefined
    tn = type(v).__name__
    if tn == "String":
        return str(v)
    if tn == "Number":
        f = float(v)
        return int(f) if f.is_integer() and abs(f) < 1e16 else f
    if type(v) is list or tn in ("Array", "NodeList"):
        return JSArray(_unwrap_js(x) for x in v)
    return v


def _delegate_method(kind, value, key):
    """Fall through to ``domonic.javascript.<kind>`` for a String / Array /
    Number method the interpreter does not implement itself. domonic's
    instance methods are spec-solid and return primitives; this keeps the
    interpreter a thin shell over them instead of reimplementing badly."""
    try:
        proxy = _js_type("Array")(*value) if kind == "Array" else _js_type(kind)(value)
        attr = getattr(proxy, key)
    except Exception:
        return UNDEFINED
    if attr is None:
        return UNDEFINED
    if not callable(attr):
        return _unwrap_js(attr)

    def wrapped(*args):
        try:
            return _unwrap_js(attr(*args))
        except JSThrow:
            raise
        except Exception as ex:  # a domonic call blew up
            raise JSThrow(_make_error(_JS_ERR_NAME.get(type(ex).__name__, "Error"), str(ex)))
    return wrapped


def _array_method(arr, key):
    import functools
    m = {
        "push": lambda *a: (arr.extend(a), len(arr))[1],
        "pop": lambda: arr.pop() if arr else UNDEFINED,
        "shift": lambda: arr.pop(0) if arr else UNDEFINED,
        "unshift": lambda *a: (arr.__setitem__(slice(0, 0), list(a)), len(arr))[1],
        "slice": lambda *a: JSArray(arr[slice(*[int(x) if x is not UNDEFINED else None for x in (a + (UNDEFINED, UNDEFINED))[:2]])]),
        "indexOf": lambda x, *_: arr.index(x) if x in arr else -1,
        "includes": lambda x, *_: x in arr,
        "join": lambda sep=",": _stringify(sep).join(_stringify(x) for x in arr),
        "concat": lambda *a: JSArray(list(arr) + [i for x in a for i in (x if isinstance(x, (list, JSArray)) else [x])]),
        "reverse": lambda: (arr.reverse(), arr)[1],
        "map": lambda fn, *_: JSArray(_call(fn, x, i, arr) for i, x in enumerate(arr)),
        "filter": lambda fn, *_: JSArray(x for i, x in enumerate(arr) if js_truthy(_call(fn, x, i, arr))),
        "forEach": lambda fn, *_: ([_call(fn, x, i, arr) for i, x in enumerate(arr)], UNDEFINED)[1],
        "find": lambda fn, *_: next((x for i, x in enumerate(arr) if js_truthy(_call(fn, x, i, arr))), UNDEFINED),
        "findIndex": lambda fn, *_: next((i for i, x in enumerate(arr) if js_truthy(_call(fn, x, i, arr))), -1),
        "some": lambda fn, *_: any(js_truthy(_call(fn, x, i, arr)) for i, x in enumerate(arr)),
        "every": lambda fn, *_: all(js_truthy(_call(fn, x, i, arr)) for i, x in enumerate(arr)),
        "reduce": lambda fn, *init: functools.reduce(lambda acc, ix: _call(fn, acc, ix[1], ix[0], arr), enumerate(arr), init[0]) if init else functools.reduce(lambda acc, x: _call(fn, acc, x), arr),
        "sort": lambda *fn: (arr.sort(key=functools.cmp_to_key(lambda a, b: int(js_number(_call(fn[0], a, b))))) if fn else arr.sort(key=_stringify), arr)[1],
        "splice": lambda start=0, dc=UNDEFINED, *items: _splice(arr, start, dc, items),
        "fill": lambda v=UNDEFINED, s=UNDEFINED, e=UNDEFINED, *_: _fill(arr, v, s, e),
    }
    if key in m:
        return m[key]
    return _delegate_method("Array", arr, key)


def _splice(arr, start, dc, items):
    n = len(arr)
    start = int(js_number(start))
    start = max(n + start, 0) if start < 0 else min(start, n)
    dc = (n - start) if dc is UNDEFINED else max(0, min(int(js_number(dc)), n - start))
    removed = JSArray(arr[start:start + dc])
    arr[start:start + dc] = list(items)
    return removed


def _fill(arr, v, s, e):
    n = len(arr)
    s = 0 if s is UNDEFINED else (max(n + int(s), 0) if int(s) < 0 else min(int(s), n))
    e = n if e is UNDEFINED else (max(n + int(e), 0) if int(e) < 0 else min(int(e), n))
    for i in range(s, e):
        arr[i] = v
    return arr


def _str_method(s, key):
    m = {
        "toUpperCase": lambda: s.upper(),
        "toLowerCase": lambda: s.lower(),
        "trim": lambda: s.strip(),
        "trimStart": lambda: s.lstrip(),
        "trimEnd": lambda: s.rstrip(),
        "slice": lambda *a: s[slice(*[int(x) if x is not UNDEFINED else None for x in (a + (UNDEFINED, UNDEFINED))[:2]])],
        "substring": lambda a=0, b=UNDEFINED: s[int(a):(len(s) if b is UNDEFINED else int(b))],
        "substr": lambda a=0, n=UNDEFINED: s[int(a):] if n is UNDEFINED else s[int(a):int(a) + int(n)],
        "charAt": lambda i=0: s[int(i)] if 0 <= int(i) < len(s) else "",
        "charCodeAt": lambda i=0: ord(s[int(i)]) if 0 <= int(i) < len(s) else float("nan"),
        "codePointAt": lambda i=0: ord(s[int(i)]) if 0 <= int(i) < len(s) else UNDEFINED,
        "indexOf": lambda t, *_: s.find(_stringify(t)),
        "lastIndexOf": lambda t, *_: s.rfind(_stringify(t)),
        "includes": lambda t, *_: _stringify(t) in s,
        "startsWith": lambda t, *_: s.startswith(_stringify(t)),
        "endsWith": lambda t, *_: s.endswith(_stringify(t)),
        "repeat": lambda n: s * int(n),
        "padStart": lambda n, c=" ": s.rjust(int(n), _stringify(c)[:1] or " "),
        "padEnd": lambda n, c=" ": s.ljust(int(n), _stringify(c)[:1] or " "),
        "concat": lambda *a: s + "".join(_stringify(x) for x in a),
        "at": lambda i=0: (s[int(i)] if -len(s) <= int(i) < len(s) else UNDEFINED),
        "toString": lambda: s,
        "valueOf": lambda: s,
    }
    # `replace` / `split` / `match` / `matchAll` / `search` accept a RegExp;
    # `normalize` / `localeCompare` the interpreter never had -- domonic does
    # all of them.
    if key in m:
        return m[key]
    return _delegate_method("String", s, key)


def _number_method(n, key):
    m = {
        "toString": lambda radix=UNDEFINED: (_stringify(n) if radix is UNDEFINED
                                             else _to_radix(int(n), int(radix))),
        "toFixed": lambda d=0: f"{float(n):.{int(d)}f}",
        "valueOf": lambda: n,
    }
    if key in m:
        return m[key]
    return _delegate_method("Number", n, key)


def _to_radix(n, base):
    if n == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    neg = n < 0
    n = abs(n)
    out = ""
    while n:
        out = digits[n % base] + out
        n //= base
    return ("-" if neg else "") + out


_JS_ERR_NAME = {
    "ValueError": "SyntaxError", "JSONDecodeError": "SyntaxError",
    "KeyError": "TypeError", "AttributeError": "TypeError", "TypeError": "TypeError",
    "IndexError": "RangeError", "OverflowError": "RangeError",
    "ZeroDivisionError": "RangeError", "RecursionError": "RangeError",
    "NameError": "ReferenceError",
}


def _call(fn, *args):
    if isinstance(fn, (JSFunction, JSClass)):
        return fn.__call__(*args)
    if callable(fn):
        return fn(*args)
    raise JSThrow(_make_error("TypeError", f"{_stringify(fn)} is not a function"))


# -- the interpreter ---------------------------------------------------

_BINOPS = {
    "+": js_add,
    "-": lambda a, b: js_number(a) - js_number(b),
    "*": lambda a, b: js_number(a) * js_number(b),
    "/": lambda a, b: (js_number(a) / js_number(b)) if js_number(b) != 0 else (math.inf if js_number(a) > 0 else -math.inf if js_number(a) < 0 else float("nan")),
    "%": lambda a, b: math.fmod(js_number(a), js_number(b)) if js_number(b) != 0 else float("nan"),
    "**": lambda a, b: js_number(a) ** js_number(b),
    "==": js_loose_eq,
    "!=": lambda a, b: not js_loose_eq(a, b),
    "===": js_strict_eq,
    "!==": lambda a, b: not js_strict_eq(a, b),
    "<": lambda a, b: _cmp(a, b, "<"),
    "<=": lambda a, b: _cmp(a, b, "<="),
    ">": lambda a, b: _cmp(a, b, ">"),
    ">=": lambda a, b: _cmp(a, b, ">="),
    "&": lambda a, b: _int32(a) & _int32(b),
    "|": lambda a, b: _int32(a) | _int32(b),
    "^": lambda a, b: _int32(a) ^ _int32(b),
    "<<": lambda a, b: _int32(_int32(a) << (_int32(b) & 31)),
    ">>": lambda a, b: _int32(a) >> (_int32(b) & 31),
    ">>>": lambda a, b: (_uint32(a) >> (_int32(b) & 31)),
    "instanceof": lambda a, b: _js_instanceof(a, b),
    "in": lambda a, b: _js_in(a, b),
}


def _js_in(a, b):
    if isinstance(b, dict):
        return _to_key(a) in b
    if isinstance(b, (list, JSArray)):
        try:
            return 0 <= int(a) < len(b)
        except (ValueError, TypeError):
            return False
    if type(b).__name__ == "DOMStringMap":
        return _to_key(a) in b
    return False


def _js_instanceof(a, b):
    if isinstance(a, JSInstance):
        return _is_instance(a, b)
    # Error objects are plain dicts tagged with a `name`; match against the
    # built-in error constructors (and their `Error` base).
    err_name = getattr(b, "__err_name__", None)
    if err_name is not None and isinstance(a, dict) and "name" in a:
        return a["name"] == err_name or err_name == "Error"
    bname = getattr(b, "__name__", None) or getattr(b, "name", None)
    if bname == "Array":
        return isinstance(a, (list, JSArray))
    if bname == "Object":
        return isinstance(a, (dict, list, JSArray)) or isinstance(a, JSInstance)
    if bname == "Function":
        return callable(a) or isinstance(a, (JSFunction, JSClass))
    if bname == "Promise":
        return isinstance(a, _Promise)
    if isinstance(b, type):
        try:
            return isinstance(a, b)
        except TypeError:
            return False
    return False


def _is_instance(inst, cls):
    c = inst._cls if isinstance(inst, JSInstance) else None
    while c is not None:
        if c is cls:
            return True
        c = c.superclass
    return False


def _cmp(a, b, op):
    if isinstance(a, str) and isinstance(b, str):
        x, y = a, b
    else:
        x, y = js_number(a), js_number(b)
        if _is_nan(x) or _is_nan(y):
            return False
    return {"<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y}[op]


def _int32(v):
    n = js_number(v)
    if _is_nan(n) or n in (math.inf, -math.inf):
        return 0
    n = int(n) & 0xFFFFFFFF
    return n - 0x100000000 if n >= 0x80000000 else n


def _uint32(v):
    n = js_number(v)
    if _is_nan(n) or n in (math.inf, -math.inf):
        return 0
    return int(n) & 0xFFFFFFFF


class Interpreter:
    def __init__(self, globals_=None, global_object=None):
        self.global_env = Environment()
        self.global_env.this = UNDEFINED
        self.global_env.glob = global_object
        self.loop = EventLoop()
        for k, v in (globals_ or {}).items():
            self.global_env.declare(k, v)
        self.cur_loc = None       # loc of the statement currently executing
        self.frames = ["<script>"]  # call stack of function names
        self._pending_label = None  # label a following loop should adopt
        self._current_gen = None    # the generator whose body is executing (yield target)
        self.modules = {}         # resolved path -> {"exports": JSObject, "dir": str}
        self.module_base = os.getcwd()
        self._cur_module = {"exports": JSObject(), "dir": self.module_base}
        self._install_async_globals(global_object)

    def _install_async_globals(self, window):
        loop = self.loop
        g = {
            "Promise": _make_promise_api(loop),
            "setTimeout": lambda fn, ms=0, *a: loop.timer(lambda: _call(fn, *a), js_number(ms) or 0),
            "setInterval": lambda fn, ms=0, *a: loop.timer(lambda: _call(fn, *a), js_number(ms) or 0, interval=True),
            "clearTimeout": lambda tid=None, *_: loop.clear(tid) if tid is not None else None,
            "clearInterval": lambda tid=None, *_: loop.clear(tid) if tid is not None else None,
            "queueMicrotask": lambda fn, *_: loop.micro(lambda: _call(fn)),
            "setImmediate": lambda fn, *a: loop.timer(lambda: _call(fn, *a), 0),
            "eval": self._eval_global,
        }
        for k, v in g.items():
            self.global_env.declare(k, v)
            if window is not None and hasattr(window, "_own"):
                window._own[k] = v

    def _eval_global(self, src=UNDEFINED, *_):
        """Indirect ``eval`` -- runs the source in the global scope (sloppy)."""
        if not isinstance(src, str):
            return src
        tree = Parser({"ecmaVersion": 2022, "locations": True,
                       "allowAwaitOutsideFunction": True}, src).parse()
        return self._exec_block(tree.body, self.global_env, hoist=True)

    def run(self, src, ecma_version=2022, module=None):
        if module is None:
            module = bool(_MODULE_HINT.search(src))
        opts = {"ecmaVersion": ecma_version, "locations": True,
                "allowAwaitOutsideFunction": True}
        if module:
            opts["sourceType"] = "module"
        tree = Parser(opts, src).parse()
        try:
            result = self._exec_block(tree.body, self.global_env, hoist=True)
            self.loop.run()   # flush timers / promise chains / pending I/O
            return result
        except (JSThrow, JSSyntaxError) as err:
            self._attach_trace(err)
            raise

    def _attach_trace(self, err):
        if getattr(err, "js_trace", None):
            return
        line = self.cur_loc.start.line if self.cur_loc else None
        frames = " → ".join(reversed(self.frames))
        err.js_line = line
        err.js_trace = frames
        if isinstance(err, JSThrow) and isinstance(err.value, dict) and line:
            err.value.setdefault("line", line)
            base = err.value.get("stack", err.value.get("message", ""))
            err.value["stack"] = f"{base}\n  at {frames} (line {line})"
        suffix = f" (line {line})" if line else ""
        if not str(err).endswith(suffix) and suffix:
            err.args = (str(err) + suffix,)

    # -- statements ---------------------------------------------------

    def _exec_block(self, stmts, env, hoist=False):
        if hoist:
            for s in stmts:
                if s.type == "FunctionDeclaration" and s.id:
                    env.declare(s.id.name, JSFunction(s, env, self))
        result = UNDEFINED
        for s in stmts:
            result = self.execute(s, env)
        return result

    def execute(self, node, env):
        loc = getattr(node, "loc", None)
        if loc is not None:
            self.cur_loc = loc
        t = node.type
        m = getattr(self, "_st_" + t, None)
        if m is None:
            raise JSSyntaxError(f"unsupported statement: {t}")
        return m(node, env)

    def _st_ExpressionStatement(self, n, env):
        return self.evaluate(n.expression, env)

    def _st_EmptyStatement(self, n, env):
        return UNDEFINED

    # -- ES modules -------------------------------------------------------

    def _resolve_module(self, spec, base_dir):
        if spec.startswith((".", "/")):
            path = os.path.normpath(os.path.join(base_dir, spec))
            for cand in (path, path + ".js", path + ".mjs", os.path.join(path, "index.js")):
                if os.path.isfile(cand):
                    return cand
            raise JSThrow(_make_error("Error", f"cannot find module {spec!r} from {base_dir}"))
        return spec  # bare specifier -> Python module

    def _load_module(self, spec, base_dir):
        key = self._resolve_module(spec, base_dir)
        if key in self.modules:
            return self.modules[key]["exports"]

        if not key.startswith((".", "/")) and not os.path.isabs(key):
            # bare specifier: expose a Python module as an ES module
            try:
                pymod = importlib.import_module(key)
            except ImportError as ex:
                raise JSThrow(_make_error("Error", f"cannot import {spec!r}: {ex}"))
            exports = JSObject({n: getattr(pymod, n) for n in dir(pymod) if not n.startswith("_")})
            exports["default"] = pymod
            self.modules[key] = {"exports": exports, "dir": base_dir}
            return exports

        with open(key, encoding="utf-8") as fh:
            src = fh.read()
        exports = JSObject()
        entry = {"exports": exports, "dir": os.path.dirname(key)}
        self.modules[key] = entry  # register before executing (cycle tolerance)
        mod_env = Environment(self.global_env)
        mod_env.this = UNDEFINED
        prev = self._cur_module
        self._cur_module = entry
        try:
            tree = Parser({"ecmaVersion": 2022, "locations": True, "sourceType": "module",
                           "allowAwaitOutsideFunction": True}, src).parse()
            self._exec_block(tree.body, mod_env, hoist=True)
        finally:
            self._cur_module = prev
        return exports

    def _st_ImportDeclaration(self, n, env):
        exports = self._load_module(n.source.value, self._cur_module["dir"])
        for spec in n.specifiers:
            if spec.type == "ImportDefaultSpecifier":
                env.declare(spec.local.name, exports.get("default", UNDEFINED))
            elif spec.type == "ImportNamespaceSpecifier":
                env.declare(spec.local.name, exports)
            else:  # ImportSpecifier
                name = spec.imported.name if spec.imported.type == "Identifier" else _to_key(spec.imported.value)
                env.declare(spec.local.name, exports.get(name, UNDEFINED))
        return UNDEFINED

    def _st_ExportNamedDeclaration(self, n, env):
        exp = self._cur_module["exports"]
        if getattr(n, "declaration", None):
            self.execute(n.declaration, env)
            decl = n.declaration
            if decl.type == "VariableDeclaration":
                for d in decl.declarations:
                    for name in self._pattern_names(d.id):
                        exp[name] = env.get(name)
            elif getattr(decl, "id", None):
                exp[decl.id.name] = env.get(decl.id.name)
            return UNDEFINED
        src_exports = self._load_module(n.source.value, self._cur_module["dir"]) if getattr(n, "source", None) else None
        for spec in n.specifiers:
            local = spec.local.name if spec.local.type == "Identifier" else _to_key(spec.local.value)
            name = spec.exported.name if spec.exported.type == "Identifier" else _to_key(spec.exported.value)
            exp[name] = src_exports.get(local, UNDEFINED) if src_exports is not None else env.get(local)
        return UNDEFINED

    def _st_ExportDefaultDeclaration(self, n, env):
        d = n.declaration
        if d.type in ("FunctionDeclaration", "ClassDeclaration") and getattr(d, "id", None):
            self.execute(d, env)
            self._cur_module["exports"]["default"] = env.get(d.id.name)
        elif d.type == "FunctionDeclaration":
            self._cur_module["exports"]["default"] = JSFunction(d, env, self)
        elif d.type == "ClassDeclaration":
            self._cur_module["exports"]["default"] = self._make_class(d, env)
        else:
            self._cur_module["exports"]["default"] = self.evaluate(d, env)
        return UNDEFINED

    def _st_ExportAllDeclaration(self, n, env):
        exports = self._load_module(n.source.value, self._cur_module["dir"])
        target = self._cur_module["exports"]
        if getattr(n, "exported", None):  # export * as ns from '...'
            target[n.exported.name] = exports
        else:
            for k, v in exports.items():
                if k != "default":
                    target[k] = v
        return UNDEFINED

    def _pattern_names(self, node):
        t = node.type
        if t == "Identifier":
            return [node.name]
        if t == "ObjectPattern":
            out = []
            for p in node.properties:
                out += self._pattern_names(p.argument if p.type == "RestElement" else p.value)
            return out
        if t == "ArrayPattern":
            return [nm for el in node.elements if el is not None
                    for nm in self._pattern_names(el.argument if el.type == "RestElement" else el)]
        if t == "AssignmentPattern":
            return self._pattern_names(node.left)
        if t == "RestElement":
            return self._pattern_names(node.argument)
        return []

    def _st_VariableDeclaration(self, n, env):
        is_const = n.kind == "const"
        for d in n.declarations:
            value = self.evaluate(d.init, env) if getattr(d, "init", None) else UNDEFINED
            self._bind_pattern(d.id, value, env, declare=True)
            if is_const:
                for nm in self._pattern_names(d.id):
                    if env.consts is None:
                        env.consts = set()
                    env.consts.add(nm)
        return UNDEFINED

    def _st_FunctionDeclaration(self, n, env):
        env.declare(n.id.name, JSFunction(n, env, self))
        return UNDEFINED

    def _st_ClassDeclaration(self, n, env):
        env.declare(n.id.name, self._make_class(n, env))
        return UNDEFINED

    def _st_ReturnStatement(self, n, env):
        raise _Return(self.evaluate(n.argument, env) if getattr(n, "argument", None) else UNDEFINED)

    def _st_IfStatement(self, n, env):
        if js_truthy(self.evaluate(n.test, env)):
            return self.execute(n.consequent, env)
        elif getattr(n, "alternate", None):
            return self.execute(n.alternate, env)
        return UNDEFINED

    def _st_BlockStatement(self, n, env):
        return self._exec_block(n.body, Environment(env), hoist=True)

    def _take_label(self):
        lbl = self._pending_label
        self._pending_label = None
        return lbl

    @staticmethod
    def _for_this_loop(exc, label):
        return exc.label is None or exc.label == label

    def _st_ForStatement(self, n, env):
        label = self._take_label()
        scope = Environment(env)
        let_names = []
        if getattr(n, "init", None):
            if n.init.type == "VariableDeclaration":
                self._st_VariableDeclaration(n.init, scope)
                if n.init.kind in ("let", "const"):
                    let_names = [nm for d in n.init.declarations for nm in self._pattern_names(d.id)]
            else:
                self.evaluate(n.init, scope)
        while n.test is None or js_truthy(self.evaluate(n.test, scope)):
            body_env = Environment(scope)
            for nm in let_names:   # fresh per-iteration binding for closures
                body_env.declare(nm, scope.get(nm))
            try:
                self.execute(n.body, body_env)
            except _Break as b:
                if self._for_this_loop(b, label):
                    break
                raise
            except _Continue as c:
                if not self._for_this_loop(c, label):
                    raise
            finally:
                for nm in let_names:  # copy any writes back so `i++` sees them
                    scope.vars[nm] = body_env.vars[nm]
            if getattr(n, "update", None):
                self.evaluate(n.update, scope)
        return UNDEFINED

    def _st_WhileStatement(self, n, env):
        label = self._take_label()
        while js_truthy(self.evaluate(n.test, env)):
            try:
                self.execute(n.body, Environment(env))
            except _Break as b:
                if self._for_this_loop(b, label):
                    break
                raise
            except _Continue as c:
                if self._for_this_loop(c, label):
                    continue
                raise
        return UNDEFINED

    def _st_DoWhileStatement(self, n, env):
        label = self._take_label()
        while True:
            try:
                self.execute(n.body, Environment(env))
            except _Break as b:
                if self._for_this_loop(b, label):
                    break
                raise
            except _Continue as c:
                if not self._for_this_loop(c, label):
                    raise
            if not js_truthy(self.evaluate(n.test, env)):
                break
        return UNDEFINED

    def _st_ForOfStatement(self, n, env):
        label = self._take_label()
        it = self.evaluate(n.right, env)
        seq = it if isinstance(it, (list, JSArray, str)) else (list(it) if hasattr(it, "__iter__") else [])
        for item in list(seq):
            scope = Environment(env)
            self._for_target(n.left, item, scope)
            try:
                self.execute(n.body, scope)
            except _Break as b:
                if self._for_this_loop(b, label):
                    break
                raise
            except _Continue as c:
                if self._for_this_loop(c, label):
                    continue
                raise
        return UNDEFINED

    def _st_ForInStatement(self, n, env):
        label = self._take_label()
        obj = self.evaluate(n.right, env)
        if isinstance(obj, dict):
            keys = list(obj.keys())
        elif isinstance(obj, (list, JSArray)):
            keys = [str(i) for i in range(len(obj))]
        elif hasattr(obj, "keys"):  # DOMStringMap and other mapping-likes
            keys = list(obj.keys())
        else:
            keys = []
        for k in keys:
            scope = Environment(env)
            self._for_target(n.left, k, scope)
            try:
                self.execute(n.body, scope)
            except _Break as b:
                if self._for_this_loop(b, label):
                    break
                raise
            except _Continue as c:
                if self._for_this_loop(c, label):
                    continue
                raise
        return UNDEFINED

    def _for_target(self, left, value, env):
        if left.type == "VariableDeclaration":
            self._bind_pattern(left.declarations[0].id, value, env, declare=True)
        else:
            self._assign_target(left, value, env)

    def _st_BreakStatement(self, n, env):
        raise _Break(n.label.name if getattr(n, "label", None) else None)

    def _st_ContinueStatement(self, n, env):
        raise _Continue(n.label.name if getattr(n, "label", None) else None)

    def _st_SwitchStatement(self, n, env):
        disc = self.evaluate(n.discriminant, env)
        scope = Environment(env)
        matched = False
        try:
            for case in n.cases:
                if not matched:
                    if case.test is None:
                        continue
                    if js_strict_eq(disc, self.evaluate(case.test, scope)):
                        matched = True
                if matched:
                    for s in case.consequent:
                        self.execute(s, scope)
            if not matched:
                run = False
                for case in n.cases:
                    if case.test is None:
                        run = True
                    if run:
                        for s in case.consequent:
                            self.execute(s, scope)
        except _Break:
            pass
        return UNDEFINED

    def _st_TryStatement(self, n, env):
        try:
            self.execute(n.block, env)
        except (JSThrow, JSSyntaxError) as raw:
            ex = raw if isinstance(raw, JSThrow) else JSThrow(_make_error("SyntaxError", str(raw)))
            if getattr(n, "handler", None):
                scope = Environment(env)
                if n.handler.param:
                    self._bind_pattern(n.handler.param, ex.value, scope, declare=True)
                self.execute(n.handler.body, scope)
            elif not getattr(n, "finalizer", None):
                raise ex from None
        finally:
            if getattr(n, "finalizer", None):
                self.execute(n.finalizer, env)
        return UNDEFINED

    def _st_ThrowStatement(self, n, env):
        raise JSThrow(self.evaluate(n.argument, env))

    def _st_LabeledStatement(self, n, env):
        label = n.label.name
        if n.body.type in ("ForStatement", "ForInStatement", "ForOfStatement",
                           "WhileStatement", "DoWhileStatement"):
            self._pending_label = label   # the loop consumes it and owns break/continue
            return self.execute(n.body, env)
        try:
            return self.execute(n.body, env)
        except _Break as b:
            if b.label not in (None, label):
                raise
            return UNDEFINED

    # -- expressions -----------------------------------------------

    def evaluate(self, node, env):
        if node is None:
            return UNDEFINED
        loc = getattr(node, "loc", None)
        if loc is not None:
            self.cur_loc = loc
        t = node.type
        m = getattr(self, "_ex_" + t, None)
        if m is None:
            raise JSSyntaxError(f"unsupported expression: {t}")
        return m(node, env)

    def _ex_Literal(self, n, env):
        v = n.value
        return v

    def _ex_Identifier(self, n, env):
        if n.name == "undefined":
            return UNDEFINED
        return env.get(n.name)

    def _ex_ThisExpression(self, n, env):
        return env.this

    def _ex_TemplateLiteral(self, n, env):
        out = []
        exprs = list(n.expressions)
        for i, q in enumerate(n.quasis):
            out.append(q.value["cooked"] if q.value["cooked"] is not None else q.value["raw"])
            if i < len(exprs):
                out.append(_stringify(self.evaluate(exprs[i], env)))
        return "".join(out)

    def _ex_TaggedTemplateExpression(self, n, env):
        fn = self.evaluate(n.tag, env)
        strings = JSArray(q.value["cooked"] for q in n.quasi.quasis)
        strings_obj = strings
        args = [self.evaluate(e, env) for e in n.quasi.expressions]
        return _call(fn, strings_obj, *args)

    def _ex_ArrayExpression(self, n, env):
        out = JSArray()
        for el in n.elements:
            if el is None:
                out.append(UNDEFINED)
            elif el.type == "SpreadElement":
                out.extend(self.evaluate(el.argument, env))
            else:
                out.append(self.evaluate(el, env))
        return out

    def _ex_ObjectExpression(self, n, env):
        obj = JSObject()
        accessors = {}
        for p in n.properties:
            if p.type == "SpreadElement":
                src = self.evaluate(p.argument, env)
                if isinstance(src, dict):
                    obj.update(src)
                continue
            key = self._prop_key(p, env)
            if p.kind == "get":
                accessors.setdefault(key, _Accessor()).get = JSFunction(p.value, env, self)
            elif p.kind == "set":
                accessors.setdefault(key, _Accessor()).set = JSFunction(p.value, env, self)
            else:
                obj[key] = self.evaluate(p.value, env)
        if accessors:
            object.__setattr__(obj, "_accessors", accessors)
        return obj

    def _prop_key(self, p, env):
        k = p.key
        if getattr(p, "computed", False):
            return _to_key(self.evaluate(k, env))
        return k.name if k.type == "Identifier" else _to_key(k.value)

    def _ex_FunctionExpression(self, n, env):
        return JSFunction(n, env, self)

    def _ex_ArrowFunctionExpression(self, n, env):
        return JSFunction(n, env, self, is_arrow=True)

    def _ex_ClassExpression(self, n, env):
        return self._make_class(n, env)

    def _ex_YieldExpression(self, n, env):
        gen = self._current_gen
        if gen is None:
            raise JSSyntaxError("yield outside a generator")
        value = self.evaluate(n.argument, env) if getattr(n, "argument", None) else UNDEFINED
        if getattr(n, "delegate", False):  # yield*
            result = UNDEFINED
            src = value if hasattr(value, "__iter__") else []
            for item in src:
                result = gen._do_yield(item)
            return result
        return gen._do_yield(value)

    def _ex_AwaitExpression(self, n, env):
        value = self.evaluate(n.argument, env)
        if not isinstance(value, _Promise):
            return value
        self.loop.run_until(lambda: value.state != "pending")
        if value.state == "rejected":
            raise JSThrow(value.value)
        return value.value

    def _ex_UnaryExpression(self, n, env):
        op = n.operator
        if op == "typeof":
            if n.argument.type == "Identifier" and not env.has(n.argument.name):
                return "undefined"
            return js_typeof(self.evaluate(n.argument, env))
        if op == "delete":
            if n.argument.type == "MemberExpression":
                obj = self.evaluate(n.argument.object, env)
                key = self._member_key(n.argument, env)
                if isinstance(obj, dict):
                    obj.pop(_to_key(key), None)
                elif type(obj).__name__ == "DOMStringMap":
                    try:
                        del obj[_to_key(key)]
                    except (KeyError, TypeError):
                        pass
                return True
            return True
        v = self.evaluate(n.argument, env)
        if op == "!":
            return not js_truthy(v)
        if op == "-":
            return -js_number(v)
        if op == "+":
            return js_number(v)
        if op == "~":
            return ~_int32(v)
        if op == "void":
            return UNDEFINED
        raise JSSyntaxError(f"unary {op}")

    def _ex_UpdateExpression(self, n, env):
        old = js_number(self.evaluate(n.argument, env))
        new = old + 1 if n.operator == "++" else old - 1
        self._assign_target(n.argument, new, env)
        return new if n.prefix else old

    def _ex_BinaryExpression(self, n, env):
        a = self.evaluate(n.left, env)
        b = self.evaluate(n.right, env)
        fn = _BINOPS.get(n.operator)
        if fn is None:
            raise JSSyntaxError(f"binary {n.operator}")
        return fn(a, b)

    def _ex_LogicalExpression(self, n, env):
        a = self.evaluate(n.left, env)
        if n.operator == "&&":
            return self.evaluate(n.right, env) if js_truthy(a) else a
        if n.operator == "||":
            return a if js_truthy(a) else self.evaluate(n.right, env)
        if n.operator == "??":
            return a if (a is not None and a is not UNDEFINED) else self.evaluate(n.right, env)
        raise JSSyntaxError(f"logical {n.operator}")

    def _ex_ConditionalExpression(self, n, env):
        return self.evaluate(n.consequent if js_truthy(self.evaluate(n.test, env)) else n.alternate, env)

    def _ex_SequenceExpression(self, n, env):
        r = UNDEFINED
        for e in n.expressions:
            r = self.evaluate(e, env)
        return r

    def _ex_AssignmentExpression(self, n, env):
        if n.operator == "=":
            value = self.evaluate(n.right, env)
            self._assign_target(n.left, value, env, pattern=True)
            return value
        cur = self.evaluate(n.left, env)
        rhs = self.evaluate(n.right, env)
        base_op = n.operator[:-1]
        if base_op == "||":
            value = cur if js_truthy(cur) else rhs
        elif base_op == "&&":
            value = rhs if js_truthy(cur) else cur
        elif base_op == "??":
            value = cur if (cur is not None and cur is not UNDEFINED) else rhs
        else:
            value = _BINOPS[base_op](cur, rhs)
        self._assign_target(n.left, value, env)
        return value

    def _member_key(self, node, env):
        if getattr(node, "computed", False):
            return self.evaluate(node.property, env)
        return node.property.name

    def _ex_MemberExpression(self, n, env):
        obj = self.evaluate(n.object, env)
        if getattr(n, "optional", False) and (obj is None or obj is UNDEFINED):
            return UNDEFINED
        return js_get(obj, self._member_key(n, env))

    def _ex_ChainExpression(self, n, env):
        try:
            return self.evaluate(n.expression, env)
        except JSThrow:
            return UNDEFINED

    def _ex_CallExpression(self, n, env):
        callee = n.callee
        this = UNDEFINED
        if callee.type == "Super":
            # super(...) -- run the superclass constructor against `this`
            sup = env.get("__superclass__")
            args = self._args(n.arguments, env)
            if isinstance(sup, JSClass):
                sup._construct(env.this, args)
            elif isinstance(sup, JSFunction):
                sup.__call__(*args, _this=env.this)
            return UNDEFINED
        if callee.type == "MemberExpression":
            obj = self.evaluate(callee.object, env)
            if getattr(callee, "optional", False) and (obj is None or obj is UNDEFINED):
                return UNDEFINED
            key = self._member_key(callee, env)
            if callee.object.type == "Super":
                # super.m() -> the superclass method, but `this` stays the instance
                this = env.this
                m = obj.method(key) if isinstance(obj, JSClass) else None
                fn = _bound(m, this) if m is not None else js_get(obj, key)
            else:
                this = obj
                fn = js_get(obj, key)
        else:
            fn = self.evaluate(callee, env)
        if getattr(n, "optional", False) and (fn is None or fn is UNDEFINED):
            return UNDEFINED
        args = self._args(n.arguments, env)
        return self._invoke(fn, args, this)

    def _invoke(self, fn, args, this):
        if isinstance(fn, JSFunction):
            return fn.__call__(*args, _this=this)
        if isinstance(fn, JSClass):
            raise JSThrow(_make_error("TypeError", f"Class constructor {fn.name} cannot be invoked without 'new'"))
        if callable(fn):
            try:
                return fn(*args)
            except JSThrow:
                raise
            except (_Return, _Break, _Continue):
                raise
            except Exception as ex:  # a native (domonic / Python) call blew up
                raise JSThrow(_make_error(_JS_ERR_NAME.get(type(ex).__name__, "Error"), str(ex)))
        raise JSThrow(_make_error("TypeError", f"{_stringify(fn)} is not a function"))

    def _ex_NewExpression(self, n, env):
        cls = self.evaluate(n.callee, env)
        args = self._args(n.arguments, env)
        if isinstance(cls, JSClass):
            return cls.__call__(*args, _new=True)
        if isinstance(cls, JSFunction):
            inst = JSObject()
            ret = cls.__call__(*args, _this=inst, _new=True)
            return ret if isinstance(ret, (dict, JSObject)) else inst
        if callable(cls):
            return cls(*args)
        raise JSThrow(_make_error("TypeError", f"{_stringify(cls)} is not a constructor"))

    def _ex_Super(self, n, env):
        return env.get("__superclass__")

    def _args(self, nodes, env):
        out = []
        for a in nodes:
            if a.type == "SpreadElement":
                out.extend(self.evaluate(a.argument, env))
            else:
                out.append(self.evaluate(a, env))
        return out

    # -- patterns & assignment -------------------------------------

    def _bind_params(self, params, args, env):
        for i, p in enumerate(params):
            if p.type == "RestElement":
                env.declare(p.argument.name, JSArray(args[i:]))
                return
            val = args[i] if i < len(args) else UNDEFINED
            self._bind_pattern(p, val, env, declare=True)

    def _bind_pattern(self, target, value, env, declare=False):
        t = target.type
        if t == "Identifier":
            (env.declare if declare else env.set)(target.name, value)
        elif t == "AssignmentPattern":
            if value is UNDEFINED:
                value = self.evaluate(target.right, env)
            self._bind_pattern(target.left, value, env, declare)
        elif t == "ArrayPattern":
            seq = list(value) if isinstance(value, (list, JSArray, str)) else []
            for i, el in enumerate(target.elements):
                if el is None:
                    continue
                if el.type == "RestElement":
                    self._bind_pattern(el.argument, JSArray(seq[i:]), env, declare)
                    break
                self._bind_pattern(el, seq[i] if i < len(seq) else UNDEFINED, env, declare)
        elif t == "ObjectPattern":
            taken = set()
            for p in target.properties:
                if p.type == "RestElement":
                    rest = JSObject({k: v for k, v in (value.items() if isinstance(value, dict) else []) if k not in taken})
                    self._bind_pattern(p.argument, rest, env, declare)
                    continue
                key = self._prop_key(p, env)
                taken.add(key)
                self._bind_pattern(p.value, js_get(value, key), env, declare)
        else:
            raise JSSyntaxError(f"pattern {t}")

    def _assign_target(self, target, value, env, pattern=False):
        t = target.type
        if t == "Identifier":
            env.set(target.name, value)
        elif t == "MemberExpression":
            obj = self.evaluate(target.object, env)
            js_set(obj, self._member_key(target, env), value)
        elif pattern and t in ("ArrayPattern", "ObjectPattern", "AssignmentPattern"):
            self._bind_pattern(target, value, env, declare=False)
        elif t == "ArrayExpression":  # destructuring assignment `[a,b] = ...`
            seq = list(value) if isinstance(value, (list, JSArray, str)) else []
            for i, el in enumerate(target.elements):
                if el is None:
                    continue
                self._assign_target(el, seq[i] if i < len(seq) else UNDEFINED, env, pattern=True)
        elif t == "ObjectExpression":
            for p in target.properties:
                key = self._prop_key(p, env)
                self._assign_target(p.value, js_get(value, key), env, pattern=True)
        else:
            raise JSSyntaxError(f"assign target {t}")

    # -- classes --------------------------------------------------

    def _make_class(self, node, env):
        superclass = self.evaluate(node.superClass, env) if getattr(node, "superClass", None) else None
        ctor = None
        methods = {}
        statics = {}
        fields = []
        cls_env = Environment(env)
        if superclass is not None:
            cls_env.declare("__superclass__", superclass)
        accessors = {}

        def member_key(el):
            k = el.key
            if getattr(el, "computed", False):
                return _to_key(self.evaluate(k, cls_env))
            return k.name if k.type in ("Identifier", "PrivateIdentifier") else _to_key(k.value)

        for el in node.body.body:
            if el.type == "MethodDefinition":
                key = member_key(el)
                fn = JSFunction(el.value, cls_env, self, name=key)
                if el.kind == "constructor":
                    ctor = fn
                elif el.kind == "get":
                    accessors.setdefault(key, _Accessor()).get = fn
                elif el.kind == "set":
                    accessors.setdefault(key, _Accessor()).set = fn
                elif el.static:
                    statics[key] = fn
                else:
                    methods[key] = fn
            elif el.type == "PropertyDefinition":
                key = member_key(el)
                if el.static:
                    statics[key] = self.evaluate(el.value, env) if getattr(el, "value", None) else UNDEFINED
                else:
                    fields.append((key, getattr(el, "value", None), cls_env))
        name = node.id.name if getattr(node, "id", None) else ""
        return JSClass(name, ctor, methods, statics, superclass, self, fields, accessors)


# -- default global environment (domonic) ------------------------------


def _make_string_ctor():
    """A JS ``String`` that yields real Python ``str`` (domonic's
    ``javascript.String`` is a wrapper object the interpreter's coercions do not
    recognise). domonic's static helpers are copied across."""
    def String(*a, _this=UNDEFINED, _new=False):
        return "" if not a else _stringify(a[0])
    try:
        import domonic.javascript as _js
        for n in ("fromCharCode", "fromCodePoint", "raw"):
            if hasattr(_js.String, n):
                setattr(String, n, getattr(_js.String, n))
    except Exception:  # pragma: no cover
        pass
    String.name = String.__name__ = "String"
    return String


def _number_ctor(*a, _this=UNDEFINED, _new=False):
    return 0 if not a else js_number(a[0])


_number_ctor.name = _number_ctor.__name__ = "Number"


def _boolean_ctor(*a, _this=UNDEFINED, _new=False):
    return js_truthy(a[0]) if a else False


_boolean_ctor.name = _boolean_ctor.__name__ = "Boolean"


def _array_ctor(*a, _this=UNDEFINED, _new=False):
    if len(a) == 1 and isinstance(a[0], (int, float)) and not isinstance(a[0], bool):
        return JSArray([UNDEFINED] * int(a[0]))
    return JSArray(a)


def _array_from(src=UNDEFINED, mapfn=UNDEFINED, *_):
    if src is UNDEFINED or src is None:
        return JSArray()
    if isinstance(src, dict) and "length" in src:
        items = [src.get(str(i), UNDEFINED) for i in range(int(js_number(src["length"])))]
    elif isinstance(src, str):
        items = list(src)
    elif hasattr(src, "__iter__"):
        items = list(src)
    else:
        items = []
    if callable(mapfn):
        items = [_invoke_any(mapfn, [x, i], None) for i, x in enumerate(items)]
    return JSArray(items)


_array_ctor.name = _array_ctor.__name__ = "Array"
_array_ctor.isArray = lambda v=UNDEFINED, *_: isinstance(v, (list, JSArray))
_array_ctor.of = lambda *a: JSArray(a)
_array_ctor.from_ = _array_from
setattr(_array_ctor, "from", _array_from)


_number_ctor.isInteger = staticmethod(
    lambda v=UNDEFINED, *_: isinstance(v, (int, float)) and not isinstance(v, bool)
    and not _is_nan(v) and float(v).is_integer())
_number_ctor.isNaN = staticmethod(lambda v=UNDEFINED, *_: isinstance(v, float) and v != v)
_number_ctor.isFinite = staticmethod(
    lambda v=UNDEFINED, *_: isinstance(v, (int, float)) and not isinstance(v, bool)
    and v not in (math.inf, -math.inf) and v == v)
_number_ctor.parseFloat = staticmethod(lambda v=UNDEFINED, *_: js_number(v))
_number_ctor.parseInt = staticmethod(lambda v=UNDEFINED, *_: int(js_number(v)) if not _is_nan(js_number(v)) else float("nan"))
_number_ctor.MAX_SAFE_INTEGER = 2 ** 53 - 1
_number_ctor.MIN_SAFE_INTEGER = -(2 ** 53 - 1)
_number_ctor.MAX_VALUE = 1.7976931348623157e308
_number_ctor.MIN_VALUE = 5e-324
_number_ctor.EPSILON = 2.220446049250313e-16
_number_ctor.POSITIVE_INFINITY = math.inf
_number_ctor.NEGATIVE_INFINITY = -math.inf
_number_ctor.NaN = float("nan")
_number_ctor.isSafeInteger = staticmethod(
    lambda v=UNDEFINED, *_: isinstance(v, (int, float)) and not isinstance(v, bool)
    and not _is_nan(v) and float(v).is_integer() and abs(v) <= 2 ** 53 - 1)


def _object_assign(target, *sources):
    for s in sources:
        if isinstance(s, dict):
            target.update(s)
        elif hasattr(s, "keys"):
            for k in s.keys():
                target[_to_key(k)] = s[k]
    return target


def _object_freeze(o, *_):
    if isinstance(o, JSObject):
        object.__setattr__(o, "_frozen", True)
    return o


def _object_define_property(o, key, desc, *_):
    key = _to_key(key)
    if isinstance(desc, dict) and isinstance(o, dict):
        if "value" in desc:
            o[key] = desc["value"]
        elif callable(desc.get("get")) or callable(desc.get("set")):
            acc = getattr(o, "_accessors", None)
            if acc is None:
                acc = {}
                object.__setattr__(o, "_accessors", acc)
            a = acc.setdefault(key, _Accessor())
            if callable(desc.get("get")):
                a.get = _thunk_accessor(desc["get"])
            if callable(desc.get("set")):
                a.set = _thunk_accessor(desc["set"])
    return o


class _thunk_accessor:
    """Wrap a plain callable so ``_Accessor`` can call it with ``_this=``."""

    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args, _this=UNDEFINED, _new=False):
        try:
            return self.fn(*args, _this=_this)
        except TypeError:
            return self.fn(*args)


def _obj_descriptor(o, key, *_):
    key = _to_key(key)
    if isinstance(o, dict) and key in o:
        return JSObject({"value": o[key], "writable": True,
                         "enumerable": True, "configurable": True})
    return UNDEFINED


_JSON_SKIP = object()


def _make_json_ns():
    import json as _pyjson

    def _to_plain(v, replacer):
        if v is UNDEFINED:
            return _JSON_SKIP
        if isinstance(v, bool) or v is None or isinstance(v, (int, float, str)):
            return v
        if isinstance(v, (JSFunction, JSClass)) or (callable(v) and not isinstance(v, type)):
            return _JSON_SKIP
        if isinstance(v, dict):
            out = {}
            for k, val in v.items():
                if callable(replacer):
                    val = _invoke_any(replacer, [k, val], v)
                p = _to_plain(val, replacer)
                if p is not _JSON_SKIP:
                    out[str(k)] = p
            return out
        if isinstance(v, (list, JSArray)):
            return [None if _to_plain(x, replacer) is _JSON_SKIP else _to_plain(x, replacer) for x in v]
        return _JSON_SKIP

    def stringify(value=UNDEFINED, replacer=UNDEFINED, space=UNDEFINED, *_):
        indent = int(space) if isinstance(space, (int, float)) and not isinstance(space, bool) else (
            space if isinstance(space, str) and space else None)
        top = value
        if callable(replacer):
            top = _invoke_any(replacer, ["", value], None)
        plain = _to_plain(top, replacer if callable(replacer) else None)
        if plain is _JSON_SKIP:
            return UNDEFINED
        seps = (",", ": ") if indent is not None else (",", ":")
        return _pyjson.dumps(plain, indent=indent, separators=seps, ensure_ascii=False)

    def _wrap(v):
        if isinstance(v, dict):
            return JSObject({k: _wrap(x) for k, x in v.items()})
        if isinstance(v, list):
            return JSArray(_wrap(x) for x in v)
        return v

    def parse(text=UNDEFINED, reviver=UNDEFINED, *_):
        try:
            data = _pyjson.loads(_stringify(text))
        except (ValueError, TypeError) as ex:
            raise JSThrow(_make_error("SyntaxError", str(ex)))
        result = _wrap(data)
        if not callable(reviver):
            return result

        def walk(holder, key):
            val = holder[key]
            if isinstance(val, dict):
                for k in list(val.keys()):
                    nv = walk(val, k)
                    if nv is UNDEFINED:
                        del val[k]
                    else:
                        val[k] = nv
            elif isinstance(val, list):
                for i in range(len(val)):
                    val[i] = walk(val, i)
            return _invoke_any(reviver, [str(key), val], holder)

        return walk(JSObject({"": result}), "")

    ns = JSObject()
    ns.update({"stringify": stringify, "parse": parse})
    return ns


def _make_object_ns():
    ns = JSObject()
    ns.update({
        "keys": lambda o=UNDEFINED, *_: JSArray(o.keys()) if isinstance(o, dict) else JSArray(),
        "values": lambda o=UNDEFINED, *_: JSArray(o.values()) if isinstance(o, dict) else JSArray(),
        "entries": lambda o=UNDEFINED, *_: JSArray(JSArray([k, v]) for k, v in o.items()) if isinstance(o, dict) else JSArray(),
        "assign": _object_assign,
        "freeze": _object_freeze,
        "isFrozen": lambda o=UNDEFINED, *_: bool(_intern(o, "_frozen")),
        "fromEntries": lambda it=(), *_: JSObject({_to_key(k): v for k, v in it}),
        "getOwnPropertyNames": lambda o=UNDEFINED, *_: JSArray(o.keys()) if isinstance(o, dict) else JSArray(),
        "getOwnPropertyDescriptor": _obj_descriptor,
        "create": lambda proto=None, props=UNDEFINED, *_: JSObject(),
        "defineProperty": _object_define_property,
        "getPrototypeOf": lambda o=UNDEFINED, *_: None,
        "setPrototypeOf": lambda o=UNDEFINED, p=UNDEFINED, *_: o,
        "preventExtensions": lambda o=UNDEFINED, *_: o,
    })
    return ns


class _Math:
    PI = math.pi
    E = math.e
    abs = staticmethod(lambda x: abs(js_number(x)))
    floor = staticmethod(lambda x: math.floor(js_number(x)))
    ceil = staticmethod(lambda x: math.ceil(js_number(x)))
    round = staticmethod(lambda x: math.floor(js_number(x) + 0.5))
    trunc = staticmethod(lambda x: math.trunc(js_number(x)))
    sign = staticmethod(lambda x: (js_number(x) > 0) - (js_number(x) < 0))
    sqrt = staticmethod(lambda x: math.sqrt(js_number(x)))
    cbrt = staticmethod(lambda x: math.copysign(abs(js_number(x)) ** (1 / 3), js_number(x)))
    pow = staticmethod(lambda a, b: js_number(a) ** js_number(b))
    hypot = staticmethod(lambda *a: math.hypot(*(js_number(x) for x in a)))
    max = staticmethod(lambda *a: max((js_number(x) for x in a), default=-math.inf))
    min = staticmethod(lambda *a: min((js_number(x) for x in a), default=math.inf))
    log = staticmethod(lambda x: math.log(js_number(x)))
    log2 = staticmethod(lambda x: math.log2(js_number(x)))
    log10 = staticmethod(lambda x: math.log10(js_number(x)))
    exp = staticmethod(lambda x: math.exp(js_number(x)))
    sin = staticmethod(lambda x: math.sin(js_number(x)))
    cos = staticmethod(lambda x: math.cos(js_number(x)))
    tan = staticmethod(lambda x: math.tan(js_number(x)))
    atan2 = staticmethod(lambda y, x: math.atan2(js_number(y), js_number(x)))

    @staticmethod
    def random():
        import random as _r
        return _r.random()


def _error_ctor(name):
    def ctor(*a, _this=UNDEFINED, _new=False):
        e = JSObject()
        e["name"] = name
        e["message"] = _stringify(a[0]) if a else ""
        e["stack"] = f"{name}: {e['message']}"
        return e
    ctor.__repr__ = lambda: f"function {name}() {{ [native code] }}"
    ctor.name = name           # JS: TypeError.name === "TypeError"
    ctor.__err_name__ = name   # matched by `instanceof` (see _BINOPS)
    return ctor


class _Console:
    def __init__(self):
        self.lines = []

    def log(self, *a):
        self.lines.append(" ".join(_stringify(x) for x in a))

    warn = error = info = debug = trace = log


class _Doc:
    """An isolated document -- ``<html><body>`` -- backed by a real domonic
    ``Document``, so ``createElement`` / ``appendChild`` build a live Python
    tree. Anything not defined here (``createComment``, ``createEvent``,
    ``evaluate``, ``importNode``, ``cookie``, ``title``, ...) forwards to the
    backing Document."""

    def __init__(self):
        from domonic.dom import Document
        from domonic.html import body as _body
        from domonic.html import head as _head
        from domonic.html import html as _html
        object.__setattr__(self, "_backing", Document())
        object.__setattr__(self, "documentElement", _html(_head(), _body()))
        object.__setattr__(self, "head", self.documentElement.getElementsByTagName("head")[0])
        object.__setattr__(self, "body", self.documentElement.getElementsByTagName("body")[0])

    def createElement(self, tag):
        return self._backing.createElement(str(tag))

    def createElementNS(self, ns, tag):
        return self._backing.createElementNS(str(ns), str(tag))

    def createTextNode(self, text):
        return self._backing.createTextNode(_stringify(text))

    def createDocumentFragment(self):
        return self._backing.createDocumentFragment()

    def getElementById(self, i):
        for el in self.documentElement.getElementsByTagName("*"):
            if getattr(el, "id", None) == str(i):
                return el
        return None

    def getElementsByTagName(self, name):
        return JSArray(self.documentElement.getElementsByTagName(str(name)))

    def getElementsByClassName(self, name):
        return JSArray(self.documentElement.getElementsByClassName(str(name)))

    def querySelector(self, sel):
        res = self.documentElement.querySelectorAll(str(sel))
        return res[0] if res else None

    def querySelectorAll(self, sel):
        return JSArray(self.documentElement.querySelectorAll(str(sel)))

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(object.__getattribute__(self, "_backing"), name, UNDEFINED)


# names in domonic.* that are helpers / ABCs / internals, not real JS globals
_GLOBAL_DENYLIST = {
    "Any", "Callable", "Iterable", "IterableABC", "Mapping", "MappingABC",
    "Sequence", "Iterator", "Global", "Pool", "Job", "ProgramKilled",
    "SetInterval", "PropertyDict", "ObjectEntries", "ArrayItems", "FetchedSet",
    "ToInt32", "ToUint32", "parserinfo", "parsedate_to_datetime", "as_signed",
    "as_unsigned", "timezone", "Window", "WorkerGlobalScope",
    "DedicatedWorkerGlobalScope", "SSEClient", "GamepadManager",
    "TextEncoderEncodeIntoResult", "ParentNode", "ChildNode", "AbastractRange",
    "DOMConfig", "DOMTimeStamp", "vec3", "parse", "function", "quote", "unquote",
    "Console", "Node", "Element", "Document", "Text", "Comment", "Attr",
    "CharacterData", "Entity", "EntityReference", "Notation", "MathMLElement",
    "XMLDocument", "NodeFilter", "PerformanceEntry",
}


def _collect_domonic_globals():
    """Auto-bind every public constructor across ``domonic.javascript``,
    ``domonic.webapi.*`` and the ``domonic.dom`` spec interfaces, so JS ``new
    X()`` works for whatever domonic implements (and fails loudly for what it
    does not -- which is the point)."""
    import importlib
    import inspect
    import pkgutil

    out = {}

    def take(mod):
        for n, o in vars(mod).items():
            if n.startswith("_") or n in _GLOBAL_DENYLIST or n in out:
                continue
            if n.startswith("HTML") and n != "HTMLElement":
                continue  # per-tag element classes -- not usefully constructable
            if (inspect.isclass(o) and n[:1].isupper()
                    and getattr(o, "__module__", "").startswith("domonic")):
                out[n] = o
            elif callable(o) and not inspect.ismodule(o) and n[:1].islower() \
                    and n in ("setTimeout", "setInterval", "clearTimeout", "clearInterval",
                              "encodeURI", "decodeURI", "parseInt", "parseFloat"):
                out[n] = o

    try:
        take(importlib.import_module("domonic.javascript"))
    except Exception:  # pragma: no cover
        pass
    try:
        wapi = importlib.import_module("domonic.webapi")
        for m in pkgutil.iter_modules(wapi.__path__):
            try:
                take(importlib.import_module(f"domonic.webapi.{m.name}"))
            except Exception:  # pragma: no cover
                pass
    except Exception:  # pragma: no cover
        pass
    try:
        take(importlib.import_module("domonic.dom"))
    except Exception:  # pragma: no cover
        pass

    out.setdefault("CustomEvent", out.get("Event"))
    return out


_DOMONIC_GLOBALS = None


class _Window:
    """The interpreter's global object. Explicit entries (``console`` /
    ``document`` isolated per run, the ``Math`` shim, the ``Error`` family) win;
    the rest is every public constructor in ``domonic.javascript`` /
    ``domonic.webapi.*`` / ``domonic.dom``; anything still unresolved forwards
    to domonic's real ``window`` (``location`` / ``navigator`` / ``atob`` / …)."""

    def __init__(self, console, document):
        global _DOMONIC_GLOBALS
        import domonic.javascript as _js
        try:
            from domonic.window import window as _dw
        except Exception:  # pragma: no cover
            _dw = None
        object.__setattr__(self, "_dw", _dw)

        if _DOMONIC_GLOBALS is None:
            _DOMONIC_GLOBALS = _collect_domonic_globals()

        own = dict(_DOMONIC_GLOBALS)
        own.update({
            "console": console,
            "document": document,
            "window": self,
            "self": self,
            "globalThis": self,
            "Math": _Math,
            "Object": _make_object_ns(),
            "Array": _array_ctor,
            "String": _make_string_ctor(),
            "Number": _number_ctor,
            "Boolean": _boolean_ctor,
            "JSON": _make_json_ns(),
            "Error": _error_ctor("Error"),
            "TypeError": _error_ctor("TypeError"),
            "RangeError": _error_ctor("RangeError"),
            "SyntaxError": _error_ctor("SyntaxError"),
            "ReferenceError": _error_ctor("ReferenceError"),
            "EvalError": _error_ctor("EvalError"),
            "URIError": _error_ctor("URIError"),
            "AggregateError": _error_ctor("AggregateError"),
            "isNaN": lambda v: _is_nan(js_number(v)),
            "isFinite": lambda v: not _is_nan(js_number(v)) and js_number(v) not in (math.inf, -math.inf),
            "NaN": float("nan"),
            "Infinity": math.inf,
            "undefined": UNDEFINED,
            "queueMicrotask": lambda fn: _call(fn),
            "structuredClone": lambda v: __import__("copy").deepcopy(v),
        })
        own.setdefault("WeakMap", own.get("Map", dict))
        own.setdefault("WeakSet", own.get("Set", set))
        object.__setattr__(self, "_own", own)

    def __getattr__(self, name):
        own = object.__getattribute__(self, "_own")
        if name in own:
            return own[name]
        dw = object.__getattribute__(self, "_dw")
        return getattr(dw, name, UNDEFINED) if dw is not None else UNDEFINED

    def __setattr__(self, name, value):
        object.__getattribute__(self, "_own")[name] = value


def default_globals(document=None):
    console = _Console()
    document = document or _Doc()
    window = _Window(console, document)
    return dict(window._own), console, document, window


def make_interpreter(extra_globals=None, console=None, document=None):
    """Build an :class:`Interpreter` wired to a fresh domonic ``window`` /
    ``document`` / ``console``, with ``extra_globals`` merged into the global
    object (and reachable as ``window.<name>``). Returns
    ``(interpreter, console, document, window)``. Callers drive it with repeated
    ``interpreter.run(src)`` -- state accumulates in one global scope, which is
    what a REPL or an embedding host wants."""
    console = console if console is not None else _Console()
    document = document or _Doc()
    window = _Window(console, document)
    for k, v in (extra_globals or {}).items():
        window._own[k] = v
    interp = Interpreter(dict(window._own), global_object=window)
    return interp, console, document, window


def run_js(src, globals_=None, ecma_version=2022):
    """Run ``src`` and return ``(document, console_lines)``.

    With no ``globals_`` a fresh domonic ``document`` (``<html><body>``) plus a
    ``console`` capture are provided; the returned document reflects whatever the
    script built.
    """
    if globals_ is None:
        g, console, document, window = default_globals()
    else:
        g = dict(globals_)
        console = g.get("console")
        document = g.get("document")
        window = g.get("window")
    Interpreter(g, global_object=window).run(src, ecma_version=ecma_version)
    lines = console.lines if console is not None and hasattr(console, "lines") else []
    return document, lines
