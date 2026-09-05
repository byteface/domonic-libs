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
import functools
import heapq
import importlib
import inspect
import keyword
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
    __slots__ = ("vars", "parent", "this", "glob", "consts", "is_call_scope")

    def __init__(self, parent=None, this=UNDEFINED, is_call_scope=False):
        self.vars = {}
        self.parent = parent
        self.this = this if this is not UNDEFINED or parent is None else parent.this
        self.glob = None  # only the root env carries the global object
        self.consts = None  # set of names declared `const` in this scope
        # a function call (or the global/module top level) -- where `var`
        # actually lands. Every OTHER Environment (a `{ }` block, a loop's
        # own per-iteration scope, a `catch` clause, ...) is block-scoped
        # only for `let`/`const`; `var` walks up past all of those to here,
        # matching real JS (`var` is function-scoped, not block-scoped).
        self.is_call_scope = is_call_scope or parent is None

    def var_scope(self):
        env = self
        while not env.is_call_scope and env.parent is not None:
            env = env.parent
        return env

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


@functools.lru_cache(maxsize=None)
def _is_staticmethod(cls, key):
    """Whether ``cls`` (or a base of it) declares ``key`` as a real
    ``@staticmethod``/``@classmethod`` -- ``getattr(cls, key)`` unwraps both
    of those to a directly-callable function, indistinguishable by shape from
    an ordinary unbound instance method (which needs a receiver), so this
    walks the MRO's own ``__dict__``s, the one place the distinction still
    shows. Cached: ``(cls, key)`` is a small, fixed, whole-program-lifetime
    set (real Python classes, not user data) walked on every native
    class/callable property miss -- e.g. every single `Math.sqrt` lookup in
    a hot loop -- found via a benchmarking pass, not a correctness bug."""
    for base in cls.__mro__:
        raw = base.__dict__.get(key)
        if raw is not None:
            return isinstance(raw, (staticmethod, classmethod))
    return False


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
        env = Environment(self.closure, this=(self.closure.this if self.is_arrow else _this), is_call_scope=True)
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
            env = Environment(fn.closure, this=(fn.closure.this if fn.is_arrow else this), is_call_scope=True)
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
        while isinstance(cls, JSClass):
            if name in cls.methods:
                return cls.methods[name]
            cls = cls.superclass
        return None

    def accessor(self, name):
        cls = self
        while isinstance(cls, JSClass):
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
        if isinstance(v, JSFunction):
            return repr(v)
        # a native (Python/domonic) function or class exposed as a JS global,
        # e.g. `String(ArrayBuffer)` -- `v.__repr__` is an *unbound* method on
        # a class (it needs `self`), so calling it directly crashes; build the
        # native-function string real JS would produce instead.
        name = getattr(v, "__name__", None) or getattr(v, "name", None) or ""
        if not isinstance(name, str):
            name = ""
        return f"function {name}() {{ [native code] }}"
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
        # symbols are opaque strings under the hood (see _symbol_ctor) --
        # real, "just barely" symbols, not real unique primitives. Without
        # this they self-report as "string" and every `typeof x === "symbol"`
        # feature-detection idiom (extremely common in real-world libraries)
        # silently takes the wrong branch.
        return "symbol" if v.startswith("@@") else "string"
    if callable(v) or isinstance(v, (JSFunction, JSClass)):
        return "function"
    return "object"


def _to_key(v):
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return _stringify(v)
    return _stringify(v)


_ERR_NS = None


def _make_error(name, message):
    """A JS error -- a real ``domonic.javascript`` error instance (1.6 ships the
    whole family with `.name` / `.message` / `.stack` and working `instanceof`)."""
    global _ERR_NS
    if _ERR_NS is None:
        import domonic.javascript as _j
        _ERR_NS = _j
    cls = getattr(_ERR_NS, name, _ERR_NS.Error)
    return cls(_stringify(message))


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
        extra = _intern(obj, key)   # e.g. a tagged template's `strings.raw`
        if extra is not None:
            return extra
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
        # classic ES5 prototypal inheritance -- `new SomeFunction()` links the
        # instance to `SomeFunction.prototype` (see _ex_NewExpression), so a
        # method assigned via `Foo.prototype.bar = ...` (or a whole prototype
        # object swapped in) is visible on every instance, walking the chain.
        proto = _intern(obj, "_proto_")
        if isinstance(proto, dict) and proto is not obj:
            return js_get(proto, key)
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
    if key.isdigit() and hasattr(obj, "__getitem__"):
        # a domonic TypedArray (Uint8Array, ...) or other array-like Python
        # object with real __getitem__ -- read through it, not getattr, or
        # `u[0]` would resolve to an attribute literally named "0" (always
        # UNDEFINED) instead of the buffer's actual element.
        try:
            return obj[int(key)]
        except (IndexError, KeyError, TypeError):
            pass
    # domonic element / JSFunction / arbitrary python object
    got = getattr(obj, key, UNDEFINED)
    if inspect.isfunction(got) and isinstance(obj, type) and not _is_staticmethod(obj, key):
        # an *unbound* Python instance method, retrieved off a class exposed
        # as a JS global itself (e.g. `Function.toString()` -- a common
        # borrowed-method feature-detection pattern where `Function` is
        # called on directly, with no instance). Calling it with no receiver
        # would crash with a raw Python "missing 1 required positional
        # argument: 'self'"; treat it as absent instead of leaking that. A
        # real `@staticmethod` (`Math.sqrt`, ...) needs no receiver at all --
        # `getattr` unwraps it to the same plain-function shape, so it must
        # be told apart by how the class itself actually declared it.
        got = UNDEFINED
    if got is UNDEFINED and keyword.iskeyword(key):
        got = getattr(obj, key + "_", UNDEFINED)   # domonic uses from_/with_/... for keywords
    if got is UNDEFINED and (callable(obj) or isinstance(obj, type)):
        if key == "prototype":
            return _generic_prototype_for(obj)
        # every function/class is itself an *object* that inherits the
        # handful of standard `Object.prototype` names (`toString`,
        # `hasOwnProperty`, ...) via `Function.prototype`, so a constructor
        # that doesn't define its own resolves there instead of coming back
        # undefined -- real code leans on exactly this (`Function.toString
        # .call(x)` is how `luxon` checks whether `x` is native, no
        # `.prototype` in sight). This is deliberately NOT the same as the
        # `.prototype`-touching borrowed-method path above: `_GenericPrototype
        # .__contains__` always answers True (so a `.call`/`.apply` on a
        # method borrowed off `.prototype` can defer to the real receiver's
        # own type later), so checking membership through it here would
        # wrongly turn *every* genuinely-missing property on *any*
        # function/class -- `SomeCtor.aTypoedStaticMethod`, `ze.accessor`
        # when `ze` really never got one -- into a callable stand-in instead
        # of the `undefined` real JS would give it. Only the actual fixed
        # Object.prototype names are safe to hand out this way.
        if key in _OBJECT_PROTO_OWN_NAMES:
            return _generic_prototype_for(obj)[key]
    if got is None and key in _STRINGY_DOM_ATTRS:
        return ""   # DOMString attributes are "" when unset, never null
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


def _accepts_this(fn):
    """Whether a native (Python-backed) callable declares a ``_this``
    keyword -- checked via its real signature, never by calling it, so a
    function with side effects is never invoked twice to find out. Cached
    by identity where possible: ``inspect.signature`` is one of the slower
    stdlib introspection calls, and re-deriving it on every single
    ``.call``/``.apply`` invocation of the *same* underlying function --
    the common case, e.g. a borrowed method captured once and called in a
    loop -- showed up as ~16% of total time in a benchmarking pass on
    exactly that pattern."""
    try:
        return _accepts_this_cached(fn)
    except TypeError:
        return _accepts_this_uncached(fn)   # fn isn't hashable -- rare, skip the cache


@functools.lru_cache(maxsize=2048)
def _accepts_this_cached(fn):
    return _accepts_this_uncached(fn)


def _accepts_this_uncached(fn):
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == "_this" or p.kind == p.VAR_KEYWORD for p in params)


def _invoke_any(fn, args, this):
    if isinstance(fn, JSFunction):
        return fn.__call__(*args, _this=this)
    if not callable(fn):
        # e.g. `SomeCtor.prototype.aMethodThatDoesntExistOnThis.call(x)` --
        # a borrowed method deferred until `.call`/`.apply` supplies the real
        # receiver (see `_GenericPrototype`) can resolve to genuinely
        # nothing once `x`'s own type is known; that's a real JS
        # "is not a function", not a raw Python crash.
        raise JSThrow(_make_error("TypeError", f"{_stringify(fn)} is not a function"))
    if this is not UNDEFINED and _accepts_this(fn):
        # a native function that cares about its receiver, e.g.
        # Object.prototype.toString.call(x) -- everything else is called
        # exactly as before.
        return fn(*args, _this=this)
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
    if isinstance(obj, JSClass):
        # a static property attached *after* the class declaration --
        # `SomeClass.create = (params) => ...` outside the class body, a
        # real, common pattern (this is exactly how zod attaches its type
        # factories: `ZodString.create = (params) => new ZodString(...)`).
        # `js_get`'s JSClass branch only ever consults `.statics`/`.methods`,
        # so the write has to land there too, not as a generic Python
        # attribute nothing will ever look at again.
        obj.statics[key] = value
        return value
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
    if key in _STRINGY_DOM_ATTRS and not isinstance(value, str):
        value = _stringify(value)   # JS coerces these to string on assignment
    if key.isdigit() and hasattr(obj, "__setitem__"):
        # a domonic TypedArray or other array-like -- write through __setitem__,
        # or `u[0] = 66` would silently create an attribute named "0" instead
        # of touching the real buffer (see the matching read in js_get).
        try:
            obj[int(key)] = value
            return value
        except (IndexError, KeyError, TypeError):
            pass
    try:
        setattr(obj, key, value)
    except Exception:
        pass
    return value


# IDL `attribute DOMString ...` -- assignment coerces to string in JS, and
# domonic corrupts the descriptor if handed a non-string.
_STRINGY_DOM_ATTRS = frozenset({
    "textContent", "innerHTML", "outerHTML", "innerText", "nodeValue", "value",
    "className", "id", "title", "alt", "href", "src", "name", "lang", "dir",
    "placeholder", "type", "rel", "target", "content", "action", "method",
    "htmlFor", "accessKey", "tabIndex", "role",
})


_JS_TYPES = {}


def _js_type(name):
    if name not in _JS_TYPES:
        import domonic.javascript as _j
        _JS_TYPES[name] = getattr(_j, name)
    return _JS_TYPES[name]


def _tuplefix(v):
    """A Python ``tuple`` from a native call is a JS array (``Map.entries()``,
    ``URLSearchParams`` iteration, ...). Convert, and dig one level into a list
    that holds tuples."""
    if isinstance(v, tuple):
        return JSArray(_tuplefix(x) for x in v)
    if type(v) is list and any(type(x) is tuple for x in v):
        return JSArray(_tuplefix(x) for x in v)
    return v


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
        # NOT int(...) here -- truncating the comparator's result toward zero
        # collapses any two elements less than 1 apart (e.g. 187.8 vs 188.0)
        # to "equal", silently leaving them in their original order.
        "sort": lambda *fn: (arr.sort(key=functools.cmp_to_key(lambda a, b: js_number(_call(fn[0], a, b)))) if fn else arr.sort(key=_stringify), arr)[1],
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
        # a boxed string (`Object("z")`, per real JS) has its own indices as
        # real, enumerable own properties -- `"z".propertyIsEnumerable(0)`
        # (a classic ES5-shim feature check, e.g. lodash/handlebars testing
        # whether they need an `Object.keys` polyfill) reads that straight
        # off the primitive rather than needing a real wrapper object.
        "propertyIsEnumerable": lambda i=0, *_: isinstance(i, (int, float)) and 0 <= int(i) < len(s),
        "hasOwnProperty": lambda k="", *_: k == "length" or (str(k).lstrip("-").isdigit() and 0 <= int(k) < len(s)),
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


# AST node type -> the *unbound* `Interpreter._ex_*` / `_st_*` method that
# handles it, populated once right after the class body below. `evaluate` /
# `execute` used to do `getattr(self, "_ex_" + node.type, None)` -- a string
# concatenation plus a full attribute lookup through the MRO, on literally
# every single node evaluated -- found via a benchmarking pass (the single
# most-called function in the whole interpreter). A plain dict keyed by the
# node-type string, populated once, is a dict lookup instead; storing the
# *unbound* function (not a bound method) keeps this correct across however
# many separate `Interpreter` instances exist in the same process, since a
# bound method captures one specific instance and can't be shared.
_EX_DISPATCH: dict = {}
_ST_DISPATCH: dict = {}


class Interpreter:
    def __init__(self, globals_=None, global_object=None, commonjs=False):
        self.global_env = Environment()
        # sloppy-mode `this` -- top-level code, and any plain (non-arrow, no
        # explicit receiver) function call, resolves `this` to the global
        # object, not undefined. Environment.__init__ already makes a new
        # scope inherit its parent's `this` whenever it isn't given one
        # explicitly (that's what makes an arrow function's lexical `this`
        # work), so setting it once here on the root env is enough to fix it
        # everywhere a bare call bottoms out at global scope.
        self.global_env.this = global_object if global_object is not None else UNDEFINED
        self.global_env.glob = global_object
        self.loop = EventLoop()
        for k, v in (globals_ or {}).items():
            self.global_env.declare(k, v)
        self.cur_loc = None       # loc of the statement currently executing
        self.frames = ["<script>"]  # call stack of function names
        self._pending_label = None  # label a following loop should adopt
        self._current_gen = None    # the generator whose body is executing (yield target)
        self.modules = {}         # resolved path -> {"exports": JSObject, "dir": str} (ES `import`)
        self.cjs_modules = {}     # resolved path/spec -> {"exports": ...} (CommonJS `require`)
        self.module_base = os.getcwd()
        self._cur_module = {"exports": JSObject(), "dir": self.module_base}
        self._install_async_globals(global_object)
        if commonjs:
            self._install_commonjs_globals()

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
        if isinstance(err, JSThrow) and line:
            v = err.value
            if isinstance(v, dict):
                v.setdefault("line", line)
                base = v.get("stack", v.get("message", ""))
                v["stack"] = f"{base}\n  at {frames} (line {line})"
            elif hasattr(v, "stack"):   # a domonic error instance
                try:
                    v.line = line
                    v.stack = f"{v.stack}\n  at {frames} (line {line})"
                except Exception:
                    pass
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
        m = _ST_DISPATCH.get(node.type)
        if m is None:
            raise JSSyntaxError(f"unsupported statement: {node.type}")
        return m(self, node, env)

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
        mod_env = Environment(self.global_env, is_call_scope=True)
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

    # -- CommonJS (`require` / `module.exports`) ---------------------------
    #
    # A real, big cluster of real-world bundles are plain CommonJS, not
    # browser UMD -- found via the `domonic_libs.realworld` sweep: roughly
    # half of its load failures are exactly `require`/`module`/`exports is
    # not defined`. But `commonjs=True` is opt-in, NOT the default, for a
    # real reason found the hard way: almost every UMD bundle (lodash,
    # dayjs, chroma, Fuse, Mustache, katex, zod, ...) picks its own export
    # style with `typeof exports === 'object' && typeof module !== "undefined"
    # ? module.exports = factory() : ... : global.TheLib = factory()` --
    # *merely the presence* of `module`/`exports` (never mind whether
    # anything ever calls `require`) makes that check true and sends a UMD
    # bundle down the Node branch, attaching to `module.exports` instead of
    # a global the rest of the page (and every curated smoke test) expects
    # to find. Turning this on by default regressed dozens of libraries
    # that already loaded fine to fix ~15 that don't -- a bad trade, since
    # a real browser has no `module`/`exports`/`require` either, and this
    # interpreter is a browser stand-in first. `myjs`'s own `require` (with
    # `fs`/`path`/`http`/... built-ins) is unaffected either way -- it was
    # always present and never included `module`/`exports`.

    def _install_commonjs_globals(self):
        module_obj = JSObject({"exports": JSObject()})
        self.global_env.declare("module", module_obj)
        self.global_env.declare("exports", module_obj["exports"])
        self.global_env.declare("require", self._make_require(self.module_base))

    def _make_require(self, base_dir):
        def require(spec=UNDEFINED, *_):
            if not isinstance(spec, str):
                raise JSThrow(_make_error("TypeError", f"The \"id\" argument must be of type string"))
            return self._require(spec, base_dir)
        return require

    def _require(self, spec, base_dir):
        key = self._resolve_module(spec, base_dir)
        if key in self.cjs_modules:
            return self.cjs_modules[key]["exports"]

        if not key.startswith((".", "/")) and not os.path.isabs(key):
            # bare specifier -- a real Python module, the same convention
            # `import x from "some_python_module"` already uses.
            name = key[5:] if key.startswith("node:") else key   # `require("node:fs")`
            try:
                pymod = importlib.import_module(name)
            except ImportError as ex:
                raise JSThrow(_make_error("Error", f"Cannot find module {spec!r}: {ex}"))
            exports = JSObject({n: getattr(pymod, n) for n in dir(pymod) if not n.startswith("_")})
            exports["default"] = pymod
            entry = {"exports": exports}
            self.cjs_modules[key] = entry
            return exports

        with open(key, encoding="utf-8") as fh:
            src = fh.read()
        mod_dir = os.path.dirname(key)
        module_obj = JSObject({"exports": JSObject()})
        self.cjs_modules[key] = module_obj   # register before executing -- circular-require tolerance
        env = Environment(self.global_env, is_call_scope=True)
        env.this = UNDEFINED
        env.declare("module", module_obj)
        env.declare("exports", module_obj["exports"])
        env.declare("require", self._make_require(mod_dir))
        env.declare("__filename", key)
        env.declare("__dirname", mod_dir)
        # a CJS file has no `import`/`export` syntax of its own -- parsed as
        # a plain script, not a module, so a top-level `return` some bundles
        # rely on (technically illegal outside a function, tolerated by
        # real Node) isn't attempted here either.
        tree = Parser({"ecmaVersion": 2022, "locations": True,
                       "allowAwaitOutsideFunction": True}, src).parse()
        self._exec_block(tree.body, env, hoist=True)
        return module_obj["exports"]

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
        # `var` is function-scoped: a `var` inside a `{ }` block, a loop body,
        # a `for(var i=0; ...)` init, ... lands in the nearest enclosing
        # function (or the global/module top level), not the block's own
        # throwaway Environment -- otherwise it vanishes with that block and
        # a later reference resolves to an unrelated outer variable of the
        # same name instead (this is exactly what broke loading `luxon`:
        # `for(var e=..., t=new Array(e), n=0; ...)` left the function's own
        # `t` invisible outside the loop). `let`/`const` stay block-scoped.
        declare_env = env.var_scope() if n.kind == "var" else env
        for d in n.declarations:
            value = self.evaluate(d.init, env) if getattr(d, "init", None) else UNDEFINED
            self._bind_pattern(d.id, value, declare_env, declare=True)
            if is_const:
                for nm in self._pattern_names(d.id):
                    if declare_env.consts is None:
                        declare_env.consts = set()
                    declare_env.consts.add(nm)
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

    def _iter_lazy(self, it):
        """Lazily yield what ``for..of`` can consume -- arrays, strings,
        generators (kept lazy so ``for (x of infiniteGen) { ...; break; }``
        works), Map/Set, other Python iterables, and objects with a
        ``[Symbol.iterator]`` method (the ``@@iterator`` key)."""
        if isinstance(it, str):
            yield from it   # JS iterates a string by code point, not code unit
            return
        if isinstance(it, (list, JSArray, tuple)):
            yield from list(it)
            return
        if isinstance(it, JSGenerator):
            yield from it
            return
        if type(it).__name__ == "Map":   # JS `[...map]` yields [k, v] pairs
            for pair in it.entries():
                yield JSArray(pair)
            return
        it_fn = js_get(it, "@@iterator") if isinstance(it, (dict, JSInstance)) else UNDEFINED
        if it_fn is not UNDEFINED and (callable(it_fn) or isinstance(it_fn, JSFunction)):
            iterator = _invoke_any(it_fn, [], it)
            nxt = js_get(iterator, "next")
            while True:
                r = _invoke_any(nxt, [], iterator)
                if js_truthy(js_get(r, "done")):
                    return
                yield js_get(r, "value")
        elif hasattr(it, "__iter__"):
            yield from it

    def _iter_values(self, it):
        return list(self._iter_lazy(it))

    def _st_ForOfStatement(self, n, env):
        label = self._take_label()
        it = self.evaluate(n.right, env)
        for item in self._iter_lazy(it):
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
            declare_env = env.var_scope() if left.kind == "var" else env
            self._bind_pattern(left.declarations[0].id, value, declare_env, declare=True)
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
        m = _EX_DISPATCH.get(node.type)
        if m is None:
            raise JSSyntaxError(f"unsupported expression: {node.type}")
        return m(self, node, env)

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
        strings = JSArray(q.value["cooked"] if q.value["cooked"] is not None else q.value["raw"]
                          for q in n.quasi.quasis)
        object.__setattr__(strings, "raw", JSArray(q.value["raw"] for q in n.quasi.quasis))
        args = [self.evaluate(e, env) for e in n.quasi.expressions]
        return _call(fn, strings, *args)

    def _ex_ArrayExpression(self, n, env):
        out = JSArray()
        for el in n.elements:
            if el is None:
                out.append(UNDEFINED)
            elif el.type == "SpreadElement":
                out.extend(self._iter_values(self.evaluate(el.argument, env)))
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
        if getattr(n, "id", None):
            # a named function expression: its own name is bound inside its body
            scope = Environment(env)
            fn = JSFunction(n, scope, self)
            scope.declare(n.id.name, fn)
            return fn
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
            elif callable(sup):
                # `class MyError extends Error` -- a real native/domonic
                # class, not something authored in JS. There's no existing
                # instance to initialise in place (native __init__ builds a
                # new object), so construct one and copy its real state
                # (message/stack/...) onto `this`, matching what `super(msg)`
                # is actually for here: making `this` behave like a real
                # Error afterward.
                try:
                    native = sup(*args)
                    for k, v in vars(native).items():
                        env.this[k] = v
                    if "name" not in env.this and hasattr(native, "name"):
                        env.this["name"] = native.name
                except Exception:  # noqa: BLE001 - a native ctor that doesn't cooperate isn't fatal
                    pass
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
                return _tuplefix(fn(*args))   # domonic returns tuples where JS wants arrays
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
            # classic `function Foo(){}` + `Foo.prototype.bar = ...` -- link
            # the new instance to the constructor's *current* prototype
            # object (not a copy), so later mutations of it stay visible and
            # `instanceof` / method lookup can walk the chain (see js_get).
            object.__setattr__(inst, "_proto_", cls.prototype)
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
                out.extend(self._iter_values(self.evaluate(a.argument, env)))
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
        elif not declare and t in ("MemberExpression", "ArrayExpression", "ObjectExpression"):
            # `[a[i], obj.x] = ...` -- assignment targets inside a pattern
            self._assign_target(target, value, env, pattern=True)
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


_EX_DISPATCH.update({name[4:]: fn for name, fn in vars(Interpreter).items() if name.startswith("_ex_")})
_ST_DISPATCH.update({name[4:]: fn for name, fn in vars(Interpreter).items() if name.startswith("_st_")})


# -- default global environment (domonic) ------------------------------


def _make_string_ctor():
    """A JS ``String``. Coercion (``String(null)`` -> ``"null"``,
    ``String([1,2])`` -> ``"1,2"``, ...) is computed by the interpreter's own
    ``_stringify`` first -- domonic has no notion of this interpreter's
    ``UNDEFINED`` sentinel, so it can't do that part -- then wrapped in
    domonic's own ``String``. Since domonic 1.7 that's a real ``str``
    *subclass* (not the disconnected wrapper object it used to be), so the
    result is both JS-faithful *and* a genuine domonic value -- indistinguishable
    from a plain ``str`` for every practical purpose (``isinstance``,
    concatenation, comparison, dict-key-matching, ``json``) except an exact
    ``type(x) is str`` check. domonic's static helpers are copied across."""
    import domonic.javascript as _js

    def String(*a, _this=UNDEFINED, _new=False):
        return _js.String("" if not a else _stringify(a[0]))
    for n in ("fromCharCode", "fromCodePoint", "raw"):
        if hasattr(_js.String, n):
            setattr(String, n, getattr(_js.String, n))
    String.name = String.__name__ = "String"
    return String


def _number_ctor(*a, _this=UNDEFINED, _new=False):
    # same shape as `String` above: `js_number` does the sentinel-aware
    # coercion, `domonic.javascript.Number` (a real `float` subclass since
    # 1.7) supplies the genuine domonic type.
    import domonic.javascript as _js
    return _js.Number(0 if not a else js_number(a[0]))


_number_ctor.name = _number_ctor.__name__ = "Number"


def _boolean_ctor(*a, _this=UNDEFINED, _new=False):
    return js_truthy(a[0]) if a else False


_boolean_ctor.name = _boolean_ctor.__name__ = "Boolean"


_SYM_COUNT = [0]


def _symbol_ctor(desc=UNDEFINED, *_a, _this=UNDEFINED, _new=False):
    """Symbols as opaque strings -- enough for ``[Symbol.iterator]() {}`` and
    ``obj[Symbol.for('k')]`` keys. Not real unique primitives."""
    _SYM_COUNT[0] += 1
    return f"@@sym:{'' if desc is UNDEFINED else _stringify(desc)}:{_SYM_COUNT[0]}"


for _w in ("iterator", "asyncIterator", "hasInstance", "toPrimitive", "toStringTag",
           "isConcatSpreadable", "species", "match", "replace", "search", "split", "unscopables"):
    setattr(_symbol_ctor, _w, f"@@{_w}")
_symbol_ctor.for_ = staticmethod(lambda k=UNDEFINED, *_: f"@@for:{_stringify(k)}")
setattr(_symbol_ctor, "for", _symbol_ctor.for_)
_symbol_ctor.keyFor = staticmethod(lambda s=UNDEFINED, *_: s[6:] if isinstance(s, str) and s.startswith("@@for:") else UNDEFINED)
_symbol_ctor.name = _symbol_ctor.__name__ = "Symbol"


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
    # `Object.assign(someFunction, {...})` -- attaching properties straight
    # onto a function object -- is real, common JS (this is exactly what
    # broke loading voca.js). `target` isn't always a plain dict; anything
    # else goes through `js_set` (JSClass -> .statics, otherwise a normal
    # attribute), the same place a direct `target.key = value` would land.
    is_plain_dict = isinstance(target, dict)
    for s in sources:
        if isinstance(s, dict):
            items = list(s.items())
        elif hasattr(s, "keys"):
            items = [(k, s[k]) for k in s.keys()]
        else:
            continue
        for k, v in items:
            if is_plain_dict:
                target[_to_key(k)] = v
            else:
                js_set(target, k, v)
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
            # plain getattr(o, "_accessors", None) doesn't work here: JSObject's
            # own __getattr__ returns UNDEFINED for a missing key instead of
            # raising, so the `None` default never actually kicks in and
            # `acc` silently ends up UNDEFINED instead of a fresh dict.
            acc = _intern(o, "_accessors")
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
        if isinstance(v, bool) or v is None or isinstance(v, str):
            return v
        if isinstance(v, (int, float)):
            # JS has one numeric type, so `Number(5)` (now a real
            # `domonic.javascript.Number` -- a `float` *subclass*, per
            # domonic 1.7 -- so a whole number stays float-backed at the C
            # level even though it should print as JS would) must not leak
            # its `.0` into the output (`JSON.stringify(Number(5))` is
            # `"5"`, not `"5.0"`); NaN / +-Infinity serialise as `null`,
            # matching domonic's own `JSON.stringify` fix for the same rule.
            if v != v or v in (math.inf, -math.inf):
                return None
            return int(v) if isinstance(v, float) and v.is_integer() else v
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


def _object_proto_to_string(*_a, _this=UNDEFINED):
    """The real ``Object.prototype.toString`` -- a standalone function that
    reads its *receiver* (``_this``, via ``.call(x)``/``.apply(x)``), not
    whatever object it happened to be looked up on. `Object.prototype.toString
    .call(x)` for robust type-tagging (``"[object Array]"``, ``"[object
    Null]"``, ...) is one of the most common idioms in real-world JS --
    lodash, Ramda, Mustache and Handlebars all reach for it just to load."""
    v = _this
    if v is UNDEFINED:
        return "[object Undefined]"
    if v is None:
        return "[object Null]"
    if isinstance(v, bool):
        return "[object Boolean]"
    if isinstance(v, (int, float)):
        return "[object Number]"
    if isinstance(v, str):
        return "[object String]"
    if isinstance(v, (list, JSArray)):
        return "[object Array]"
    if isinstance(v, (JSFunction, JSClass)) or callable(v):
        return "[object Function]"
    tag = type(v).__name__
    return f"[object {tag}]" if tag not in ("dict", "JSObject") else "[object Object]"


def _object_proto_has_own(k=UNDEFINED, *_a, _this=UNDEFINED):
    return _to_key(k) in _this if isinstance(_this, dict) else False


def _object_proto_value_of(*_a, _this=UNDEFINED):
    return _this


def _object_proto_false(*_a, _this=UNDEFINED):
    return False   # isPrototypeOf / propertyIsEnumerable -- same simplification as _plain_object_method


OBJECT_PROTOTYPE = JSObject({
    "toString": _object_proto_to_string,
    "hasOwnProperty": _object_proto_has_own,
    "valueOf": _object_proto_value_of,
    "isPrototypeOf": _object_proto_false,
    "propertyIsEnumerable": _object_proto_false,
})

_OBJECT_PROTO_OWN_NAMES = frozenset(
    {"constructor", "toString", "valueOf", "hasOwnProperty", "isPrototypeOf", "propertyIsEnumerable"}
)


class _GenericPrototype(dict):
    """``SomeBuiltin.prototype`` for a constructor with no real prototype of
    its own -- ``Array``/``Function``/``String``/``Number``/``RegExp``/
    ``Date``/... are a mix of plain interpreter functions and real domonic
    classes, neither of which define a ``.prototype``. A handful of fixed
    methods (``toString``, ``hasOwnProperty``, ...) aren't enough on their
    own: real-world code very commonly borrows a method as a standalone
    reference first and supplies the receiver later --
    ``var test = RegExp.prototype.test; test.call(re, str)`` (this is
    exactly what broke loading ``mustache.min.js``) -- rather than hand-list
    every method every builtin has, an unknown key delegates to the SAME
    per-type method resolution ``js_get`` already does when a method is
    called directly on a real value, just deferred until the receiver
    actually shows up via ``.call``/``.apply``."""

    def __init__(self, ctor):
        super().__init__({
            "constructor": ctor,
            "toString": _object_proto_to_string,
            "valueOf": _object_proto_value_of,
            "hasOwnProperty": _object_proto_has_own,
            "isPrototypeOf": _object_proto_false,
            "propertyIsEnumerable": _object_proto_false,
        })

    def __contains__(self, key):
        return True   # so `js_get`'s `if key in obj` always takes the __getitem__ path below

    def __missing__(self, key):
        def _delegated(*args, _this=UNDEFINED):
            return _invoke_any(js_get(_this, key), list(args), UNDEFINED)
        return _delegated


_GENERIC_PROTOTYPES = {}


def _generic_prototype_for(ctor):
    name = getattr(ctor, "__name__", None) or getattr(ctor, "name", None) or str(id(ctor))
    proto = _GENERIC_PROTOTYPES.get(name)
    if proto is None:
        proto = _GENERIC_PROTOTYPES[name] = _GenericPrototype(ctor)
    return proto


def _make_math_ns():
    """``Math`` -- delegates to ``domonic.javascript.Math`` for everything (the
    interpreter deleted its own ``Math`` shim in the 1.6 migration), but snaps
    ``cbrt`` / ``log2`` / ``log10`` back to the correctly-rounded result for
    the exact cases where the true answer is a whole number. Python's ``math``
    is backed by the platform libm, and glibc's ``cbrt(27)`` is
    ``3.0000000000000004`` (one ULP high) where V8 -- and macOS's libm --
    give exactly ``3``. Only snaps when the rounded result provably squares/
    cubes/exponentiates back to the input, so irrational results are
    untouched. Remove once ``domonic.javascript.Math`` rounds these itself
    (tracked in ``docs/javascript-wrinkles.md``)."""
    import domonic.javascript as _js

    def _snap(fn, inverse):
        def wrapped(x=UNDEFINED, *_a, **_kw):
            r = fn(x)
            try:
                n = round(r)
                if inverse(n) == js_number(x):
                    return float(n)
            except (TypeError, ValueError, OverflowError):
                pass
            return r
        return wrapped

    overrides = {
        "cbrt": _snap(_js.Math.cbrt, lambda n: n ** 3),
        "log2": _snap(_js.Math.log2, lambda n: 2 ** n),
        "log10": _snap(_js.Math.log10, lambda n: 10 ** n),
    }

    class _MathNS:
        def __getattr__(self, name):
            return overrides.get(name) or getattr(_js.Math, name)

    return _MathNS()


def _object_ctor_call(v=UNDEFINED, *_, _this=UNDEFINED, _new=False):
    """``Object(value)`` -- real JS: `undefined`/`null` box to a fresh empty
    object, anything already object-shaped comes back unchanged (a full,
    spec-accurate primitive-wrapper box for numbers/strings is *not* worth
    it here -- no real-world code this harness has hit relies on the boxed
    wrapper's identity being distinct from the primitive)."""
    if v is UNDEFINED or v is None:
        return JSObject()
    return v


def _make_object_ns():
    # `Object` isn't just a namespace of statics -- it's itself directly
    # callable (`Object(value)`, a common defensive-coercion idiom used by
    # lodash/handlebars/fuse.js among others); a plain `JSObject` can't be
    # called, so this builds the same real function-with-statics shape
    # `_array_ctor` uses, rather than a dict. A fresh wrapper per call (not
    # the module-level `_object_ctor_call` itself) -- every `Interpreter`
    # gets its own `Object`, so its statics stay session-isolated.
    def ns(v=UNDEFINED, *a, **kw):
        return _object_ctor_call(v, *a, **kw)
    ns.name = ns.__name__ = "Object"
    ns.prototype = OBJECT_PROTOTYPE
    ns.keys = lambda o=UNDEFINED, *_: JSArray(o.keys()) if isinstance(o, dict) else JSArray()
    ns.values = lambda o=UNDEFINED, *_: JSArray(o.values()) if isinstance(o, dict) else JSArray()
    ns.entries = lambda o=UNDEFINED, *_: JSArray(JSArray([k, v]) for k, v in o.items()) if isinstance(o, dict) else JSArray()
    ns.assign = _object_assign
    ns.freeze = _object_freeze
    ns.isFrozen = lambda o=UNDEFINED, *_: bool(_intern(o, "_frozen"))
    ns.fromEntries = lambda it=(), *_: JSObject({_to_key(k): v for k, v in it})
    ns.getOwnPropertyNames = lambda o=UNDEFINED, *_: JSArray(o.keys()) if isinstance(o, dict) else JSArray()
    ns.getOwnPropertyDescriptor = _obj_descriptor
    ns.create = lambda proto=None, props=UNDEFINED, *_: JSObject()
    ns.defineProperty = _object_define_property
    ns.getPrototypeOf = lambda o=UNDEFINED, *_: None
    ns.setPrototypeOf = lambda o=UNDEFINED, p=UNDEFINED, *_: o
    ns.preventExtensions = lambda o=UNDEFINED, *_: o
    return ns


_FMT_SPEC = re.compile(r"%[sdifoOjc%]")


def _console_format(args):
    """Apply ``%s`` / ``%d`` / ``%o`` / ``%c`` substitution like a browser."""
    if not args or not isinstance(args[0], str) or "%" not in args[0]:
        return " ".join(_stringify(x) for x in args)
    fmt, rest = args[0], list(args[1:])
    out = []
    pos = 0
    for m in _FMT_SPEC.finditer(fmt):
        out.append(fmt[pos:m.start()])
        pos = m.end()
        spec = m.group()
        if spec == "%%":
            out.append("%")
        elif spec == "%c":
            if rest:
                rest.pop(0)   # CSS -- ignored in a text console
        elif not rest:
            out.append(spec)
        elif spec in ("%d", "%i"):
            n = js_number(rest.pop(0))
            out.append("NaN" if _is_nan(n) else str(int(n)))
        elif spec == "%f":
            out.append(_stringify(js_number(rest.pop(0))))
        else:  # %s %o %O %j
            out.append(_stringify(rest.pop(0)))
    out.append(fmt[pos:])
    tail = "".join(out)
    return " ".join([tail] + [_stringify(x) for x in rest])


class _Console:
    def __init__(self):
        self.lines = []
        self._groups = 0
        self._counts = {}
        self._timers = {}

    def _emit(self, text, stream="out"):
        self.lines.append(("  " * self._groups) + text)
        return UNDEFINED   # console methods are `-> undefined` in JS

    def log(self, *a):
        return self._emit(_console_format(a))

    info = debug = log

    def warn(self, *a):
        return self._emit(_console_format(a), "err")

    error = trace = warn

    def dir(self, *a):
        return self._emit(_console_format(a))

    def assert_(self, cond=UNDEFINED, *a):
        if not js_truthy(cond):
            self._emit("Assertion failed" + (": " + _console_format(a) if a else ""), "err")
        return UNDEFINED

    def group(self, *a):
        if a:
            self._emit(_console_format(a))
        self._groups += 1
        return UNDEFINED

    groupCollapsed = group

    def groupEnd(self, *_):
        self._groups = max(0, self._groups - 1)

    def count(self, label="default", *_):
        label = _stringify(label)
        self._counts[label] = self._counts.get(label, 0) + 1
        self._emit(f"{label}: {self._counts[label]}")

    def countReset(self, label="default", *_):
        self._counts[_stringify(label)] = 0

    def time(self, label="default", *_):
        import time as _t
        self._timers[_stringify(label)] = _t.perf_counter()

    def timeEnd(self, label="default", *_):
        import time as _t
        label = _stringify(label)
        t0 = self._timers.pop(label, None)
        if t0 is not None:
            self._emit(f"{label}: {(_t.perf_counter() - t0) * 1000:.3f}ms")

    timeLog = timeEnd

    def table(self, data=UNDEFINED, *_):
        rows = list(data) if isinstance(data, (list, JSArray)) else (
            list(data.items()) if isinstance(data, dict) else [])
        if not rows:
            self._emit(_stringify(data))
            return
        if isinstance(data, dict):
            cols = ["(key)", "Values"]
            body = [[_stringify(k), _stringify(v)] for k, v in rows]
        else:
            keys = []
            for r in rows:
                if isinstance(r, dict):
                    for k in r:
                        if k not in keys:
                            keys.append(k)
            if keys:
                cols = ["(index)"] + keys
                body = [[str(i)] + [_stringify(r.get(k, "")) if isinstance(r, dict) else ""
                                    for k in keys] for i, r in enumerate(rows)]
            else:
                cols = ["(index)", "Values"]
                body = [[str(i), _stringify(r)] for i, r in enumerate(rows)]
        widths = [max(len(cols[c]), *(len(row[c]) for row in body)) for c in range(len(cols))]
        line = lambda cells: "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"
        self._emit(line(cols))
        self._emit("|" + "|".join("-" * (w + 2) for w in widths) + "|")
        for row in body:
            self._emit(line(row))

    def clear(self, *_):
        self.lines.clear()


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
            "Math": _make_math_ns(),   # domonic's Math + a correctly-rounded cbrt/log2/log10
            "Object": _make_object_ns(),
            "Array": _array_ctor,
            "Symbol": _symbol_ctor,
            "String": _make_string_ctor(),
            "Number": _number_ctor,
            "Boolean": _boolean_ctor,
            "JSON": _make_json_ns(),
            "Error": _js.Error,   # domonic 1.6: the whole error family, real classes
            "TypeError": _js.TypeError,
            "RangeError": _js.RangeError,
            "SyntaxError": _js.SyntaxError,
            "ReferenceError": _js.ReferenceError,
            "EvalError": _js.EvalError,
            "URIError": _js.URIError,
            "AggregateError": _js.AggregateError,
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


def make_interpreter(extra_globals=None, console=None, document=None, commonjs=False):
    """Build an :class:`Interpreter` wired to a fresh domonic ``window`` /
    ``document`` / ``console``, with ``extra_globals`` merged into the global
    object (and reachable as ``window.<name>``). Returns
    ``(interpreter, console, document, window)``. Callers drive it with repeated
    ``interpreter.run(src)`` -- state accumulates in one global scope, which is
    what a REPL or an embedding host wants.

    ``commonjs=True`` adds `module` / `exports` / a bare-bones `require` --
    off by default because *merely their presence* changes which branch a
    UMD bundle's own environment-detection takes (see `_install_commonjs_globals`);
    turn it on only for a script you know is genuinely CommonJS/Node-shaped,
    not a browser bundle."""
    console = console if console is not None else _Console()
    document = document or _Doc()
    window = _Window(console, document)
    for k, v in (extra_globals or {}).items():
        window._own[k] = v
    interp = Interpreter(dict(window._own), global_object=window, commonjs=commonjs)
    # `Interpreter.__init__` installs its own pragmatic-runtime globals
    # (`Promise`, `setTimeout`, `require`, ...) *after* the constructor's
    # `globals_`, so a caller's own version of one of those would otherwise
    # always lose -- reapply `extra_globals` on top so a richer host
    # `require` (myjs's, with real `fs`/`path`/`http`/... built-ins) wins
    # over the core interpreter's bare one.
    for k, v in (extra_globals or {}).items():
        interp.global_env.declare(k, v)
        window._own[k] = v
    return interp, console, document, window


def run_js(src, globals_=None, ecma_version=2022, commonjs=False):
    """Run ``src`` and return ``(document, console_lines)``.

    With no ``globals_`` a fresh domonic ``document`` (``<html><body>``) plus a
    ``console`` capture are provided; the returned document reflects whatever the
    script built. ``commonjs=True`` adds `module` / `exports` / `require` --
    see `Interpreter._install_commonjs_globals` for why that's opt-in.
    """
    if globals_ is None:
        g, console, document, window = default_globals()
    else:
        g = dict(globals_)
        console = g.get("console")
        document = g.get("document")
        window = g.get("window")
    Interpreter(g, global_object=window, commonjs=commonjs).run(src, ecma_version=ecma_version)
    lines = console.lines if console is not None and hasattr(console, "lines") else []
    return document, lines
