"""Host bindings for myjs -- the things that make "it's just JavaScript" land:
a filesystem (``fs``), shell (``sh``), synchronous HTTP (``http`` / ``fetch``),
a ``process`` object, and ``py`` for reaching into the whole Python ecosystem.

Everything here is synchronous on purpose -- there is no event loop yet, and a
one-liner that blocks is what reads as magic in a REPL. All of it is handed to
scripts as globals (see :func:`scope`).
"""

from __future__ import annotations

import base64 as _base64
import hashlib as _hashlib
import importlib
import json as _json
import os
import platform
import shutil
import socket as _socket
import ssl as _ssl
import subprocess
import sys
import threading
import time as _time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from domonic_libs.acorn.interpret import JSArray, JSObject


# --- fs --------------------------------------------------------------------

def _read_file(path, encoding="utf-8"):
    data = Path(path).read_bytes()
    return data if encoding in (None, "buffer", "binary") else data.decode(encoding)


def _read_bytes(path, n=None, offset=0):
    """The first ``n`` bytes of a file (or all of it), starting at ``offset``
    -- for peeking at a header (BMP, PNG, ELF, ...) without reading the whole
    file. Pair with the ``struct`` global to unpack it."""
    with open(path, "rb") as fh:
        if offset:
            fh.seek(int(offset))
        return fh.read(int(n) if n is not None else -1)


def _write_file(path, data, encoding="utf-8"):
    p = Path(path)
    if isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
    elif hasattr(data, "buffer") and hasattr(getattr(data, "buffer"), "tobytes"):
        # a JS Uint8Array/Int16Array/... (domonic.javascript.TypedArray) --
        # its backing store is a real array.array; write its actual bytes
        # rather than falling through to str(data) (a Python repr, not data).
        raw = data.buffer.tobytes()
    else:
        p.write_text(str(data), encoding=encoding)
        return len(data)
    p.write_bytes(raw)
    return len(raw)


def _append_file(path, data, encoding="utf-8"):
    with open(path, "a", encoding=encoding) as fh:
        fh.write(str(data))


def _stat(path):
    st = os.stat(path)
    return JSObject({
        "size": st.st_size,
        "mtimeMs": st.st_mtime * 1000,
        "isFile": os.path.isfile(path),
        "isDirectory": os.path.isdir(path),
        "mode": st.st_mode,
    })


def _mkdir(path, opts=None):
    recursive = bool(opts and opts.get("recursive"))
    Path(path).mkdir(parents=recursive, exist_ok=recursive)


def _rm(path, opts=None):
    opts = opts or {}
    p = Path(path)
    if p.is_dir() and opts.get("recursive"):
        shutil.rmtree(p, ignore_errors=bool(opts.get("force")))
    elif p.exists() or not opts.get("force"):
        p.unlink()


FS = {
    "readFileSync": _read_file,
    "readBytes": _read_bytes,
    "writeFileSync": _write_file,
    "appendFileSync": _append_file,
    "existsSync": lambda p: Path(p).exists(),
    "readdirSync": lambda p: JSArray(sorted(os.listdir(p))),
    "mkdirSync": _mkdir,
    "rmSync": _rm,
    "renameSync": lambda a, b: os.replace(a, b),
    "copyFileSync": lambda a, b: shutil.copyfile(a, b),
    "statSync": _stat,
    "realpathSync": lambda p: str(Path(p).resolve()),
    "cwd": os.getcwd,
}

PATH = {
    "join": lambda *parts: os.path.join(*[str(p) for p in parts]),
    "dirname": lambda p: os.path.dirname(p),
    "basename": lambda p, ext="": os.path.basename(p)[: -len(ext)] if ext and os.path.basename(p).endswith(ext) else os.path.basename(p),
    "extname": lambda p: os.path.splitext(p)[1],
    "resolve": lambda *parts: str(Path(*[str(p) for p in parts]).resolve()) if parts else os.getcwd(),
    "sep": os.sep,
}


# --- sh -------------------------------------------------------------------

class ShellResult(JSObject):
    def __init__(self, proc):
        super().__init__({
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "code": proc.returncode,
            "ok": proc.returncode == 0,
        })

    def __str__(self):
        return self["stdout"]

    def trim(self):
        return self["stdout"].strip()

    def json(self):
        return _to_js(_json.loads(self["stdout"]))

    def lines(self):
        return JSArray(self["stdout"].splitlines())


def _sh(cmd, opts=None):
    opts = opts or {}
    proc = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=opts.get("cwd"), timeout=opts.get("timeout"),
    )
    return ShellResult(proc)


def _say(text, *_):
    if sys.platform == "darwin":
        subprocess.run(["say", str(text)], check=False)
    elif sys.platform.startswith("linux") and shutil.which("espeak"):
        subprocess.run(["espeak", str(text)], check=False)
    else:
        print(f"\a(say) {text}")


def _osa(script):
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def _notify(text, title="myjs"):
    if sys.platform == "darwin":
        _osa(f'display notification {_json.dumps(str(text))} with title {_json.dumps(str(title))}')
    elif shutil.which("notify-send"):
        subprocess.run(["notify-send", str(title), str(text)], check=False)
    else:
        print(f"(notify) {title}: {text}")


def _alert(text, title="myjs"):
    if sys.platform == "darwin":
        _osa(f'display dialog {_json.dumps(str(text))} with title {_json.dumps(str(title))} '
             f'buttons {{"OK"}} default button "OK"')
    else:
        print(f"(alert) {title}: {text}")


def _open(target, *_):
    opener = {"darwin": "open", "win32": "start"}.get(sys.platform, "xdg-open")
    subprocess.run([opener, str(target)], check=False, shell=(opener == "start"))


def _prompt(text="", default="", *_):
    """A real OS input dialog (macOS). Returns the typed text, or None on Cancel."""
    if sys.platform == "darwin":
        script = (
            f'set r to display dialog {_json.dumps(str(text))} with title "myjs" '
            f'default answer {_json.dumps(str(default))}\n'
            f'return text returned of r'
        )
        r = subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)
        return r.stdout.rstrip("\n") if r.returncode == 0 else None
    try:
        return input(f"{text} ") or default
    except (EOFError, KeyboardInterrupt):
        return None


def _confirm(text="", *_):
    """A real OS Yes/OK-Cancel dialog (macOS). Returns a bool."""
    if sys.platform == "darwin":
        script = (
            f'set r to display dialog {_json.dumps(str(text))} with title "myjs" '
            f'buttons {{"Cancel", "OK"}} default button "OK"\n'
            f'return button returned of r'
        )
        r = subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)
        return r.returncode == 0 and r.stdout.strip() == "OK"
    try:
        return input(f"{text} [y/N] ").strip().lower().startswith("y")
    except (EOFError, KeyboardInterrupt):
        return False


def _choose_file(*_):
    """The native Finder file picker (macOS). Returns a path, or None on Cancel."""
    if sys.platform == "darwin":
        r = subprocess.run(["osascript", "-e", "POSIX path of (choose file)"],
                            check=False, capture_output=True, text=True)
        return r.stdout.strip() or None
    return None


def _choose_folder(*_):
    """The native Finder folder picker (macOS). Returns a path, or None on Cancel."""
    if sys.platform == "darwin":
        r = subprocess.run(["osascript", "-e", "POSIX path of (choose folder)"],
                            check=False, capture_output=True, text=True)
        return r.stdout.strip() or None
    return None


# --- clipboard -- the real system clipboard, shared with every other app ----

def _clipboard_write(text, *_):
    text = str(text)
    if sys.platform == "darwin":
        cmd = ["pbcopy"]
    elif sys.platform == "win32":
        cmd = ["clip"]
    else:
        cmd = next((c for c in (["xclip", "-selection", "clipboard"],
                                 ["xsel", "--clipboard", "--input"],
                                 ["wl-copy"]) if shutil.which(c[0])), None)
        if cmd is None:
            return False
    r = subprocess.run(cmd, input=text, text=True, check=False, shell=(sys.platform == "win32"))
    # pbcopy (and friends) hand data to the OS pasteboard server asynchronously
    # and exit before it's actually committed -- a `readText()` called right
    # after a `writeText()` can otherwise race it and read back a torn value
    # (most visible as mangled multi-byte characters). A short settle avoids it.
    _time.sleep(0.2)
    return r.returncode == 0


def _clipboard_read(*_):
    if sys.platform == "darwin":
        cmd = ["pbpaste"]
    elif sys.platform == "win32":
        cmd = ["powershell", "-noprofile", "-command", "Get-Clipboard"]
    else:
        cmd = next((c for c in (["xclip", "-selection", "clipboard", "-o"],
                                 ["xsel", "--clipboard", "--output"],
                                 ["wl-paste"]) if shutil.which(c[0])), None)
        if cmd is None:
            return None
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return r.stdout.rstrip("\r\n") if r.returncode == 0 else None


CLIPBOARD = {"readText": _clipboard_read, "writeText": _clipboard_write}


# --- http / fetch --------------------------------------------------------

class Response(JSObject):
    def __init__(self, url, status, headers, body):
        super().__init__({
            "url": url,
            "status": status,
            "ok": 200 <= status < 300,
            "headers": JSObject({k.lower(): v for k, v in headers}),
        })
        self._body = body

    # browser Response methods -- `await r.text()` / `await r.json()`. They are
    # synchronous here (the body is already in hand); `await` on the non-promise
    # result is a harmless no-op, so browser code ports unchanged.
    def text(self, *_):
        return self._body.decode("utf-8", "replace")

    def json(self, *_):
        return _to_js(_json.loads(self._body.decode("utf-8", "replace")))

    def bytes(self, *_):
        return object.__getattribute__(self, "_body")

    def bytes(self):
        return self._body


def _request(url, opts=None):
    opts = opts or {}
    data = opts.get("body")
    if data is not None and not isinstance(data, (bytes, bytearray)):
        data = str(data).encode("utf-8")
    headers = {k: str(v) for k, v in (opts.get("headers") or {}).items()}
    req = urllib.request.Request(url, data=data, headers=headers, method=opts.get("method"))
    try:
        with urllib.request.urlopen(req, timeout=opts.get("timeout", 30)) as resp:
            return Response(resp.geturl(), resp.status, resp.getheaders(), resp.read())
    except urllib.error.HTTPError as e:
        return Response(url, e.code, list(e.headers.items()), e.read())


HTTP = {
    "get": lambda url, opts=None: _request(url, {**(opts or {}), "method": "GET"}),
    "post": lambda url, body=None, opts=None: _request(url, {**(opts or {}), "method": "POST", "body": body}),
    "request": _request,
    "requestSync": _request,
    "serve": None,  # set in scope() -- needs the calling session's interpreter
}


def async_fetch(loop):
    """A real asynchronous ``fetch``: the request runs on a background thread and
    settles a promise through ``loop``, so ``await Promise.all([...])`` genuinely
    runs requests concurrently."""
    import threading

    from domonic_libs.acorn.interpret import _make_error, _Promise

    def fetch(url, opts=None):
        p = _Promise(loop)
        loop.io_start()

        def worker():
            try:
                resp = _request(url, opts)
                loop.io_finish(lambda: p._resolve(resp))
            except Exception as exc:  # noqa: BLE001
                loop.io_finish(lambda exc=exc: p._reject(_make_error("TypeError", f"fetch failed: {exc}")))

        threading.Thread(target=worker, daemon=True).start()
        return p

    return fetch


def _make_serve():
    from http.server import BaseHTTPRequestHandler, HTTPServer

    def serve(port, handler):
        class H(BaseHTTPRequestHandler):
            def _run(self):
                length = int(self.headers.get("content-length", 0) or 0)
                body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
                req = JSObject({
                    "method": self.command,
                    "path": self.path,
                    "headers": JSObject(dict(self.headers)),
                    "body": body,
                })
                out = handler(req)
                if isinstance(out, dict):
                    status = int(out.get("status", 200))
                    text = str(out.get("body", ""))
                    extra = out.get("headers") or {}
                else:
                    status, text, extra = 200, str(out), {}
                payload = text.encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", extra.get("content-type", "text/html; charset=utf-8"))
                self.send_header("content-length", str(len(payload)))
                for k, v in extra.items():
                    if k != "content-type":
                        self.send_header(k, str(v))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = do_PUT = do_DELETE = _run

            def log_message(self, *a):  # quiet
                pass

        srv = HTTPServer(("127.0.0.1", int(port)), H)
        print(f"myjs http.serve listening on http://127.0.0.1:{int(port)}  (Ctrl-C to stop)")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
        finally:
            srv.server_close()

    return serve


# --- WebSocket (RFC 6455 client, dependency-free) --------------------------

def _fire(handler, event):
    if callable(handler):
        handler(event)


class WebSocketClient:
    CONNECTING, OPEN, CLOSING, CLOSED = 0, 1, 2, 3

    def __init__(self, url, loop, protocols=None):
        self.url = url
        self.protocol = ""
        self.readyState = self.CONNECTING
        self.onopen = self.onmessage = self.onclose = self.onerror = None
        self._loop = loop
        self._sock = None
        self._buf = b""
        loop.io_start()
        threading.Thread(target=self._run, daemon=True).start()

    # -- lifecycle
    def _run(self):
        try:
            self._connect()
            self.readyState = self.OPEN
            self._loop.post(lambda: _fire(self.onopen, JSObject({"type": "open"})))
            self._read_loop()
        except Exception as exc:  # noqa: BLE001
            self._loop.post(lambda exc=exc: _fire(self.onerror, JSObject({"type": "error", "message": str(exc)})))
        finally:
            self.readyState = self.CLOSED
            try:
                self._sock.close()
            except Exception:
                pass
            self._loop.io_finish(lambda: _fire(self.onclose, JSObject({"type": "close"})))

    def _connect(self):
        u = urllib.parse.urlparse(self.url)
        port = u.port or (443 if u.scheme == "wss" else 80)
        raw = _socket.create_connection((u.hostname, port), timeout=10)
        if u.scheme == "wss":
            raw = _ssl.create_default_context().wrap_socket(raw, server_hostname=u.hostname)
        key = _base64.b64encode(os.urandom(16)).decode()
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        raw.sendall((
            f"GET {path} HTTP/1.1\r\nHost: {u.hostname}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = raw.recv(4096)
            if not chunk:
                raise ConnectionError("connection closed during handshake")
            resp += chunk
        if b" 101 " not in resp.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"handshake rejected: {resp.splitlines()[0].decode('latin1')}")
        self._sock = raw
        self._buf = resp.split(b"\r\n\r\n", 1)[1]

    # -- framing
    def _recv(self, n):
        while len(self._buf) < n:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ConnectionError("closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _read_loop(self):
        while self.readyState == self.OPEN:
            b1, b2 = self._recv(2)
            opcode = b1 & 0x0F
            length = b2 & 0x7F
            if length == 126:
                length = int.from_bytes(self._recv(2), "big")
            elif length == 127:
                length = int.from_bytes(self._recv(8), "big")
            payload = self._recv(length)
            if b2 & 0x80:
                mask = payload[:4]
                payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload[4:]))
            if opcode == 0x8:
                return
            if opcode == 0x9:
                self._frame(0xA, payload)
                continue
            if opcode in (0x1, 0x2):
                data = payload.decode("utf-8", "replace") if opcode == 0x1 else payload
                self._loop.post(lambda d=data: _fire(self.onmessage, JSObject({"type": "message", "data": d})))

    def _frame(self, opcode, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        mask = os.urandom(4)
        body = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
        header = bytes([0x80 | opcode])
        n = len(data)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + n.to_bytes(2, "big")
        else:
            header += bytes([0x80 | 127]) + n.to_bytes(8, "big")
        self._sock.sendall(header + mask + body)

    # -- JS surface
    def send(self, data):
        if self.readyState != self.OPEN:
            raise RuntimeError("WebSocket is not open")
        self._frame(0x1 if isinstance(data, str) else 0x2, data)

    def close(self, code=1000, reason=""):
        if self.readyState == self.OPEN:
            self.readyState = self.CLOSING
            try:
                self._frame(0x8, int(code).to_bytes(2, "big"))
            except Exception:
                pass

    def addEventListener(self, event, fn):
        setattr(self, "on" + event, fn)

    def removeEventListener(self, event, fn=None):
        setattr(self, "on" + event, None)


def websocket_ctor(loop):
    def WebSocket(url, protocols=None, *_):
        return WebSocketClient(url, loop, protocols)
    WebSocket.CONNECTING = 0
    WebSocket.OPEN = 1
    WebSocket.CLOSING = 2
    WebSocket.CLOSED = 3
    return WebSocket


# --- py: the whole Python ecosystem ------------------------------------------

def _to_js(v):
    if isinstance(v, dict):
        return JSObject({k: _to_js(val) for k, val in v.items()})
    if isinstance(v, (list, tuple)):
        return JSArray(_to_js(x) for x in v)
    return v


class _Py:
    """The ``py`` global. Callable -- ``py("expr")`` evaluates a Python
    expression (falling back to ``exec`` for statements) -- and carries
    ``py.import`` / ``py.exec`` / ``py.eval`` / ``py.list`` / ``py.dir`` / ...

        py("2 ** 10")                 // 1024
        py("print('hi')")             // prints, returns undefined
        const np = py.import("numpy")
        py.exec("import math\\nx = math.pi")   // -> {x: 3.14159...}
    """

    _G = {"__builtins__": __builtins__}

    def __call__(self, code="", scope=None, *_):
        import types
        code = str(code).strip()
        has_scope = isinstance(scope, dict)
        ns = dict(scope) if has_scope else {}
        try:
            return _to_js(eval(code, self._G, ns))          # noqa: S307 - explicit feature
        except SyntaxError:
            # Statements (imports, defs, classes, multi-line blocks) need a
            # *single* namespace for globals and locals -- otherwise a `def`
            # closes over `self._G` while its `import`s landed in a separate
            # `ns`, and the function can't see its own module's imports the
            # next time it runs (Python's exec-with-two-dicts "class body"
            # quirk). With no caller-supplied scope, exec straight against
            # the shared, persistent `self._G` so later `py(...)` calls can
            # see what an earlier one defined, like a real module namespace.
            target = ns if has_scope else self._G
            before = set(target)
            exec(code, self._G, target)                      # noqa: S102
            new_keys = set(target) - before
            return _to_js({k: target[k] for k in new_keys
                           if not k.startswith("__") and not isinstance(target[k], types.ModuleType)})

    # `import` is a keyword -- the interpreter reaches `py.import` through the
    # `<name>_` keyword-alias fallback in js_get.
    import_ = staticmethod(importlib.import_module)
    exec = __call__

    @staticmethod
    def eval(expr="", scope=None, *_):
        ns = dict(scope) if isinstance(scope, dict) else {}
        return _to_js(eval(str(expr), _Py._G, ns))           # noqa: S307

    list = staticmethod(lambda it, *_: JSArray(it))
    dict = staticmethod(lambda o, *_: JSObject(dict(o)))
    tuple = staticmethod(lambda it, *_: tuple(it))
    repr = staticmethod(lambda o, *_: repr(o))
    str = staticmethod(lambda o="", *_: str(o))
    int = staticmethod(lambda o=0, *_: int(o))
    float = staticmethod(lambda o=0.0, *_: float(o))
    len = staticmethod(lambda o, *_: len(o))
    dir = staticmethod(lambda o, *_: JSArray(dir(o)))
    type = staticmethod(lambda o, *_: type(o).__name__)
    getattr = staticmethod(lambda o, n, *d: getattr(o, n, *d))
    setattr = staticmethod(lambda o, n, v, *_: setattr(o, n, v))
    toJS = staticmethod(_to_js)
    globals = staticmethod(lambda *_: JSObject(dict(_Py._G)))


PY = _Py()


# --- os (Node-flavoured) -------------------------------------------------

def _totalmem():
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, AttributeError, OSError):
        return None


def _cpus():
    n = os.cpu_count() or 1
    model = platform.processor() or platform.machine()
    if sys.platform == "darwin":
        try:
            model = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, check=True,
            ).stdout.strip() or model
        except Exception:
            pass
    return JSArray(JSObject({"model": model}) for _ in range(n))


OS = {
    "platform": lambda: sys.platform if sys.platform != "win32" else "win32",
    "arch": lambda: {"AMD64": "x64", "x86_64": "x64"}.get(platform.machine(), platform.machine()),
    "type": platform.system,
    "release": platform.release,
    "version": lambda: platform.version(),
    "hostname": platform.node,
    "homedir": lambda: os.path.expanduser("~"),
    "tmpdir": lambda: __import__("tempfile").gettempdir(),
    "cpus": _cpus,
    "totalmem": _totalmem,
    "uptime": lambda: _time.clock_gettime(_time.CLOCK_MONOTONIC) if hasattr(_time, "CLOCK_MONOTONIC") else None,
    "userInfo": lambda *_: JSObject({
        "username": __import__("getpass").getuser(),
        "homedir": os.path.expanduser("~"),
        "shell": os.environ.get("SHELL"),
    }),
    "EOL": os.linesep,
    "python": platform.python_version(),
    # convenience shorthands (not Node, but handy in a REPL)
    "system": platform.system,
    "name": platform.system(),
}


# --- process --------------------------------------------------------------

def _process(myjs_version):
    return JSObject({
        "argv": JSArray(sys.argv[1:]),
        "env": JSObject(dict(os.environ)),
        "platform": sys.platform,
        "arch": platform.machine(),
        "pid": os.getpid(),
        "version": f"myjs/{myjs_version}",
        "cwd": os.getcwd,
        "chdir": os.chdir,
        "exit": lambda code=0: sys.exit(int(code)),
        "hrtime": lambda *_: _time.perf_counter_ns(),
    })


# --- assembly ------------------------------------------------------------

def scope(myjs_version="0.0.1"):
    fs = dict(FS)
    http = dict(HTTP)
    http["serve"] = _make_serve()
    os_ns = dict(OS)
    require_table = {
        "fs": fs, "path": dict(PATH), "http": http, "https": http, "os": os_ns,
        "child_process": {"exec": _sh, "execSync": lambda c, o=None: _sh(c, o)["stdout"]},
        "crypto": {
            "md5": lambda s: _hashlib.md5(str(s).encode()).hexdigest(),
            "sha256": lambda s: _hashlib.sha256(str(s).encode()).hexdigest(),
            "randomUUID": lambda: __import__("uuid").uuid4().hex,
        },
    }

    def require(name):
        if name.startswith("node:"):
            name = name[5:]
        if name in require_table and require_table[name] is not None:
            return require_table[name]
        return importlib.import_module(name)  # fall through to any Python module

    return {
        "fs": fs,
        "path": dict(PATH),
        "http": http,
        "os": os_ns,
        "sh": _sh,
        "say": _say,
        "notify": _notify,
        "alert": _alert,
        "prompt": _prompt,
        "confirm": _confirm,
        "chooseFile": _choose_file,
        "chooseFolder": _choose_folder,
        "clipboard": dict(CLIPBOARD),
        "open": _open,
        "fetchSync": _request,   # `fetch` (async) is installed per-session by the engine
        "process": _process(myjs_version),
        "py": PY,
        "struct": importlib.import_module("struct"),  # binary headers -- pack/unpack/calcsize/unpack_from
        "require": require,
        "atob": lambda s: _base64.b64decode(s).decode("utf-8", "replace"),
        "btoa": lambda s: _base64.b64encode(str(s).encode("utf-8")).decode("ascii"),
        "sleep": _time.sleep,
        "now": lambda: _time.time() * 1000,
        "hash": {
            "md5": lambda s: _hashlib.md5(str(s).encode()).hexdigest(),
            "sha256": lambda s: _hashlib.sha256(str(s).encode()).hexdigest(),
        },
    }
