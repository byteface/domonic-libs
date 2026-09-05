"""The ``myjs`` package: Session API, the ffi bridge, and the CLI."""

import ctypes.util
import struct

import pytest

import myjs
from myjs._engine import JSError, Session
from myjs.cli import main


def test_eval_returns_completion_value():
    assert myjs.eval("1 + 2 * 3") == 7
    assert myjs.eval("[1, 2, 3].map(n => n * n)") == [1, 4, 9]


def test_shared_session_persists_between_eval_calls():
    myjs.eval("globalThis.__t = 41")
    assert myjs.eval("__t + 1") == 42


def test_session_is_isolated():
    s = Session()
    s.eval("const only_here = 5")
    assert s.eval("only_here") == 5
    with pytest.raises(JSError):
        Session().eval("only_here")


def test_run_file(tmp_path):
    f = tmp_path / "s.js"
    f.write_text("const sum = [1, 2, 3, 4].reduce((a, b) => a + b, 0);\nsum;\n")
    assert myjs.run(str(f)) == 10


def test_js_error_carries_name_line_and_trace():
    with pytest.raises(JSError) as ei:
        myjs.eval("function boom() { throw new RangeError('nope'); }\nboom();")
    err = ei.value
    assert err.js_name == "RangeError"
    assert err.js_line == 1
    assert "boom" in err.js_trace


def test_dom_is_reachable():
    s = Session()
    s.eval("const d = document.createElement('p'); d.textContent = 'hi';"
           "document.body.appendChild(d);")
    assert str(s.document.body) == "<body><p>hi</p></body>"


# -- ffi --------------------------------------------------------------------

@pytest.mark.skipif(not ctypes.util.find_library("c"), reason="no libc found")
def test_ffi_calls_libc():
    s = Session()
    out = s.eval(
        "const libc = ffi.loadLibrary('c');"
        "libc.abs.argtypes = [ffi.types.int];"
        "libc.abs.restype = ffi.types.int;"
        "libc.abs(-42);"
    )
    assert out == 42


@pytest.mark.skipif(not ctypes.util.find_library("c"), reason="no libc found")
def test_ffi_string_buffer_round_trips():
    s = Session()
    out = s.eval(
        "const libc = ffi.loadLibrary('c');"
        "const buf = ffi.createStringBuffer(32);"
        "libc.strcpy.argtypes = [ffi.types.pointer, ffi.types.string];"
        "libc.strcpy(buf, 'from C');"
        "buf.value;"
    )
    assert out == "from C"


def test_ffi_fn_sugar_and_libc_libm_shorthands():
    s = Session()
    out = s.eval(
        "const libm = ffi.libm();"
        "const tgamma = libm.fn('tgamma', 'double', ['double']);"
        "const libc = ffi.libc();"
        "const abs_ = libc.fn('abs', 'int', ['int']);"
        "[tgamma(11), abs_(-42)];"
    )
    assert out == [3628800, 42]   # tgamma(11) == 10!


def test_ffi_types_table_is_present():
    s = Session()
    assert s.eval("typeof ffi.loadLibrary") == "function"
    assert s.eval("typeof ffi.types.int") in ("function", "object")
    assert s.eval("typeof ffi.callback") == "function"


def test_ffi_scope_is_per_session():
    a, b = Session(), Session()
    a.eval("ffi.types.int = 'clobbered'")
    assert b.eval("ffi.types.int") != "clobbered"


# -- host bindings (fs / sh / os / py / path) -----------------------------

def test_fs_round_trip(tmp_path):
    s = Session()
    s.interp.global_env.declare("DIR", str(tmp_path))
    out = s.eval(
        "const p = path.join(DIR, 'note.txt');"
        "fs.writeFileSync(p, 'hello fs');"
        "[fs.existsSync(p), fs.readFileSync(p), fs.readdirSync(DIR)[0]];"
    )
    assert out == [True, "hello fs", "note.txt"]


def test_fs_write_file_sync_accepts_a_typed_array(tmp_path):
    # a Uint8Array is a real binary buffer to JS code -- writeFileSync should
    # write its actual bytes, not str(the Python wrapper object)
    s = Session()
    p = tmp_path / "raw.bin"
    s.interp.global_env.declare("P", str(p))
    n = s.eval(
        "const u = new Uint8Array(3); u[0] = 66; u[1] = 77; u[2] = 255;"
        "fs.writeFileSync(P, u, 'binary');"
    )
    assert n == 3
    assert p.read_bytes() == b"\x42\x4d\xff"


def test_read_bytes_and_struct_unpack_a_binary_header(tmp_path):
    s = Session()
    p = tmp_path / "sample.bin"
    p.write_bytes(struct.pack("<2sIHH", b"BM", 1234, 0, 0) + b"\x00" * 20)
    s.interp.global_env.declare("PATH_", str(p))
    out = s.eval(
        "const buf = fs.readBytes(PATH_, 30);"
        "const [sig, size] = struct.unpack_from('<2sIHH', buf);"
        "[sig.decode('ascii'), size, buf.length];"
    )
    assert out == ["BM", 1234, 30]

    # readBytes with no length reads the whole file; an offset skips ahead
    assert s.eval(f"fs.readBytes(PATH_).length") == p.stat().st_size
    assert s.eval(f"struct.unpack_from('<2s', fs.readBytes(PATH_, 2, 0))[0].decode()") == "BM"


def test_sh_runs_a_command():
    s = Session()
    assert s.eval("sh('echo myjs-shell-ok').trim()") == "myjs-shell-ok"
    assert s.eval("sh('exit 3').code") == 3
    assert s.eval("sh('echo hi').ok") is True


def test_py_bridge_reaches_the_stdlib():
    s = Session()
    assert s.eval("py.import('math').factorial(5)") == 120
    assert s.eval("py.import('statistics').mean([2, 4, 6])") == 4
    assert s.eval("py.import('json').dumps({a: 1, b: [2, 3]})") == '{"a": 1, "b": [2, 3]}'
    assert s.eval("py.list(py.import('itertools').islice([10, 20, 30, 40], 2))") == [10, 20]


def test_py_is_callable():
    s = Session()
    assert s.eval("typeof py") == "function"
    assert s.eval("py('2 ** 10')") == 1024
    assert s.eval("py('sum([1, 2, 3, 4])')") == 10
    assert s.eval("py('sorted([3, 1, 2])')") == [1, 2, 3]
    assert s.eval("py.exec('x = 6 * 7').x") == 42               # statements via exec fallback
    assert s.eval("py('__import__(\"os\").sep')") in ("/", "\\")


def test_os_namespace_is_node_flavoured():
    s = Session()
    assert s.eval("os.platform()") in ("darwin", "linux", "win32")
    assert s.eval("os.cpus().length") >= 1
    assert s.eval("typeof os.homedir()") == "string"


def test_native_dialogs_fall_back_off_darwin(monkeypatch):
    # prompt/confirm/chooseFile/chooseFolder shell out to osascript on macOS;
    # off darwin they fall back to stdin so the globals stay usable everywhere.
    monkeypatch.setattr("myjs.host.sys.platform", "linux")
    monkeypatch.setattr("builtins.input", lambda *a: "yes")
    s = Session()
    assert s.eval("typeof prompt") == "function"
    assert s.eval("typeof confirm") == "function"
    assert s.eval("prompt('name?')") == "yes"
    assert s.eval("confirm('sure?')") is True
    assert s.eval("chooseFile()") is None
    assert s.eval("chooseFolder()") is None


def test_clipboard_round_trips_through_the_real_os_command(monkeypatch):
    # exercise the actual pbcopy/pbpaste plumbing (command shape, stdin/stdout
    # capture) without touching the real system clipboard in CI
    store = {}

    def fake_run(cmd, input=None, **kw):
        class R:
            pass
        r = R()
        if cmd[0] == "pbcopy":
            store["text"] = input
            r.returncode = 0
        elif cmd[0] == "pbpaste":
            r.returncode = 0
            r.stdout = store.get("text", "")
        else:
            r.returncode = 1
            r.stdout = ""
        return r

    monkeypatch.setattr("myjs.host.subprocess.run", fake_run)
    monkeypatch.setattr("myjs.host.sys.platform", "darwin")
    s = Session()
    assert s.eval("clipboard.writeText('hello from a test')") is True
    assert s.eval("clipboard.readText()") == "hello from a test"


def test_require_returns_builtins_and_python_modules():
    s = Session()
    assert s.eval("require('fs') === fs") is True
    assert s.eval("require('math').pi > 3.14") is True


def test_module_exports_are_opt_in_and_myjs_require_still_wins():
    # `require` has always been on by default in myjs (it was, before this
    # test existed) -- but `module`/`exports` are opt-in (`commonjs=True`),
    # same as the core interpreter and for the same reason: merely their
    # presence changes which branch a UMD library's own environment check
    # takes, losing the global almost every real one attaches instead of
    # `module.exports` (see `test_acorn_interpret.py
    # ::test_commonjs_is_opt_in_not_default`).
    s = Session()
    assert s.eval("typeof module") == "undefined"
    assert s.eval("typeof require") == "function"   # unaffected either way

    # opting in: `module`/`exports` work, and myjs's own `require` -- with
    # real `fs`/`path`/`http`/`os`/`child_process`/`crypto` built-ins --
    # still wins over the core interpreter's bare one.
    s2 = Session(commonjs=True)
    assert s2.eval("typeof module") == "object"
    s2.eval("exports.answer = 42;")
    assert s2.eval("module.exports.answer") == 42
    assert s2.eval("typeof require('path').join") == "function"
    assert s2.eval("typeof require('crypto').sha256") == "function"


def test_hash_and_base64_helpers():
    s = Session()
    assert s.eval("hash.sha256('abc').slice(0, 8)") == "ba7816bf"
    assert s.eval("atob(btoa('round trip'))") == "round trip"


def test_async_await_in_a_session():
    s = Session()
    s.eval(
        "(async () => {"
        "  const a = await new Promise(r => setTimeout(() => r(20), 5));"
        "  const b = await Promise.resolve(22);"
        "  console.log(a + b);"
        "})();"
    )
    assert s.console_lines == ["42"]


def test_async_fetch_is_concurrent():
    """Three requests to a local server that sleeps 0.4s each: concurrent
    finishes near 0.4s, serial would take ~1.2s."""
    import http.server
    import threading
    import time as _t

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            _t.sleep(0.4)
            self.send_response(200)
            self.send_header("content-length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        s = Session()
        start = _t.time()
        s.eval(
            f"(async () => {{"
            f"  const rs = await Promise.all(["
            f"    fetch('http://127.0.0.1:{port}/'),"
            f"    fetch('http://127.0.0.1:{port}/'),"
            f"    fetch('http://127.0.0.1:{port}/'),"
            f"  ]);"
            f"  console.log(rs.map(r => r.status).join(','));"
            f"}})();"
        )
        elapsed = _t.time() - start
    finally:
        srv.shutdown()
    assert s.console_lines == ["200,200,200"]
    assert elapsed < 0.9  # concurrent ~0.4s; serial would be ~1.2s


def test_http_serve_and_fetch_round_trip():
    import threading
    import time
    import urllib.request

    s = Session()
    s.interp.global_env.declare("__done", False)
    t = threading.Thread(
        target=lambda: s.eval(
            "http.serve(8931, (req) => 'path=' + req.path);"
        ),
        daemon=True,
    )
    t.start()
    time.sleep(0.5)
    try:
        body = urllib.request.urlopen("http://127.0.0.1:8931/hello", timeout=3).read().decode()
        assert body == "path=/hello"
    finally:
        pass  # daemon thread + process exit tears the server down


# -- ES modules ---------------------------------------------------------

def test_import_js_calls_a_real_js_function_from_plain_python(tmp_path):
    # a JS function is a real, directly callable Python object (JSFunction
    # implements __call__) -- no bridge, no serialization needed to call it
    # from a .py file, just a way to reach the export.
    (tmp_path / "math_utils.js").write_text(
        "export function double(x) { return x * 2; }\n"
        "export const PI_ISH = 3.14;\n"
    )
    mod = myjs.import_js(str(tmp_path / "math_utils.js"))
    assert mod.double(21) == 42            # attribute access
    assert mod["double"](21) == 42         # dict access -- same object either way
    assert mod.PI_ISH == 3.14


def test_es_modules_relative_import(tmp_path):
    (tmp_path / "lib.js").write_text(
        "export const TAU = 6.28;\n"
        "export function double(x) { return x * 2; }\n"
        "export default (x) => x * x;\n"
    )
    (tmp_path / "app.js").write_text(
        "import square, { TAU, double } from './lib.js';\n"
        "import * as lib from './lib.js';\n"
        "console.log(TAU, double(21), square(5), Object.keys(lib).sort().join(','));\n"
    )
    s = Session()
    s.run_file(str(tmp_path / "app.js"))
    assert s.console_lines == ["6.28 42 25 TAU,default,double"]


def test_es_module_bare_specifier_is_a_python_module(tmp_path):
    (tmp_path / "a.js").write_text(
        "import math from 'math';\n"
        "console.log(math.factorial(5));\n"
    )
    s = Session()
    s.run_file(str(tmp_path / "a.js"))
    assert s.console_lines == ["120"]


def test_es_module_is_cached(tmp_path):
    (tmp_path / "counter.js").write_text(
        "console.log('module body ran');\nexport const n = 1;\n"
    )
    (tmp_path / "m.js").write_text(
        "import { n } from './counter.js';\n"
        "import { n as n2 } from './counter.js';\n"
        "console.log(n + n2);\n"
    )
    s = Session()
    s.run_file(str(tmp_path / "m.js"))
    assert s.console_lines == ["module body ran", "2"]  # body ran once


# -- websocket + gui --------------------------------------------------

def test_websocket_global_is_a_constructor():
    s = Session()
    assert s.eval("typeof WebSocket") == "function"
    assert s.eval("WebSocket.OPEN") == 1


def test_websocket_echo_round_trip():
    s = Session()
    try:
        s.eval(
            "const ws = new WebSocket('wss://ws.postman-echo.com/raw');\n"
            "ws.onopen = () => ws.send('ping');\n"
            "ws.onmessage = (e) => { console.log('got ' + e.data); ws.close(); };\n"
        )
    except Exception as exc:
        pytest.skip(f"websocket endpoint unavailable: {exc}")
    if not s.console_lines:
        pytest.skip("websocket endpoint did not respond")
    assert s.console_lines == ["got ping"]


def test_render_html_serialises_the_built_dom():
    s = Session()
    s.eval(
        "document.title = 'Report';\n"
        "const h = document.createElement('h1'); h.textContent = 'Hi';\n"
        "document.body.appendChild(h);\n"
    )
    html = s.render_html()
    assert html.startswith("<!doctype html>")
    assert "<title>Report</title>" in html
    assert "<h1>Hi</h1>" in html


# -- headless HTML rendering ------------------------------------------

_PAGE = """<!doctype html><html><head><title>Start</title></head><body>
<h1 id="g">loading</h1><ul id="list"></ul><p class="s"></p>
<script>
  document.getElementById("g").textContent = "ready";
  const ul = document.getElementById("list");
  ["a","b","c"].forEach(t => { const li = document.createElement("li"); li.textContent = t.toUpperCase(); ul.appendChild(li); });
  document.title = "Done " + ul.children.length;
</script>
<script>document.addEventListener("DOMContentLoaded", () => document.querySelector(".s").textContent = "dcl");</script>
</body></html>"""


def test_page_runs_scripts_against_the_dom():
    page = myjs.Page(_PAGE)
    assert page.errors == []
    assert page.title == "Done 3"
    assert page.query("#g").textContent == "ready"
    assert [li.textContent for li in page.query_all("#list li")] == ["A", "B", "C"]
    assert page.query(".s").textContent == "dcl"      # DOMContentLoaded fired


def test_page_eval_after_render_for_scraping():
    page = myjs.Page(_PAGE)
    assert page.eval("document.querySelectorAll('li').length") == 3


def test_page_load_with_relative_module(tmp_path):
    (tmp_path / "u.js").write_text("export const shout = s => s.toUpperCase() + '!';\n")
    (tmp_path / "i.html").write_text(
        "<!doctype html><html><body><div id=x></div>"
        "<script type=module>import {shout} from './u.js';"
        "document.getElementById('x').textContent = shout('hi');</script></body></html>"
    )
    page = myjs.Page.load(str(tmp_path / "i.html"))
    assert page.errors == []
    assert page.query("#x").textContent == "HI!"


def test_page_load_from_url_fetches_html_css_and_scripts():
    # `Page.load` takes an http(s):// URL, not just a local path -- it
    # fetches the page, folds every `<link rel=stylesheet>` into the
    # document (so `getComputedStyle` sees the real rules), and fetches
    # each `<script src>`, resolving both relative to the page URL.
    import http.server
    import threading

    files = {
        "/index.html": (
            b"<!doctype html><html><head>"
            b"<link rel='stylesheet' href='app.css'>"
            b"</head><body><div id='box'>hi</div>"
            b"<script src='app.js'></script></body></html>",
            "text/html",
        ),
        "/app.css": (b"#box { color: rgb(0, 128, 0); position: absolute; }", "text/css"),
        "/app.js": (b"document.getElementById('box').setAttribute('data-ran', '1');", "application/javascript"),
    }

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body, ctype = files.get(self.path, (b"not found", "text/plain"))
            self.send_response(200 if self.path in files else 404)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        page = myjs.Page.load(f"http://127.0.0.1:{port}/index.html")
    finally:
        srv.shutdown()

    assert page.errors == []
    # the external script ran, resolved relative to the page URL
    assert page.attr("#box", "data-ran") == "1"
    # the external stylesheet's rules reach getComputedStyle
    assert page.eval("getComputedStyle(document.getElementById('box')).color") == "rgb(0, 128, 0)"
    assert page.eval("getComputedStyle(document.getElementById('box')).position") == "absolute"


def test_render_and_strip_scripts():
    html = myjs.render(_PAGE, strip_scripts=True)
    assert "<li>A</li><li>B</li><li>C</li>" in html
    assert "<script" not in html


_APP = """<!doctype html><html><body>
<form id="f"><input id="name"><button>Add</button></form>
<ul id="list"></ul><p id="count">0</p>
<script>
const list = document.getElementById("list");
document.getElementById("f").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = document.getElementById("name").value;
  const li = document.createElement("li");
  li.textContent = v;
  li.addEventListener("click", () => li.classList.toggle("done"));
  list.appendChild(li);
  document.getElementById("name").value = "";
  document.getElementById("count").textContent = list.children.length;
  setTimeout(() => { li.setAttribute("data-ready", "1"); }, 20);
});
</script></body></html>"""


def test_page_interaction_fill_submit_click():
    page = myjs.Page(_APP)
    page.fill("#name", "milk").submit("#f")
    page.fill("#name", "bread").submit("#f")
    assert page.text("#count") == "2"
    assert [li.textContent for li in page.query_all("#list li")] == ["milk", "bread"]

    page.click(page.query_all("#list li")[0])
    assert "done" in (page.query_all("#list li")[0].getAttribute("class") or "")


def test_page_wait_for_async_mutation():
    page = myjs.Page(_APP)
    page.fill("#name", "x").submit("#f")
    page.wait_for("li[data-ready='1']", timeout=2)
    assert page.exists("li[data-ready='1']")


def test_page_location_reflects_url():
    page = myjs.Page("<html><body><script>console.log(location.href, location.pathname, location.protocol)</script></body></html>",
                     url="https://example.com/a/b?q=1")
    assert page.console_lines == ["https://example.com/a/b?q=1 /a/b https:"]


def test_console_format_and_table_and_streams(capsys):
    s = Session()
    s.eval("console.log('%s = %d', 'x', 42); "
           "console.group('g'); console.log('nested'); console.groupEnd(); "
           "console.table([{a: 1, b: 2}]); "
           "console.count('c'); console.count('c');")
    lines = s.console_lines
    assert lines[0] == "x = 42"
    assert lines[2] == "  nested"
    assert any("| a" in ln and "| b" in ln for ln in lines)
    assert lines[-1] == "c: 2"


def test_console_clear_resets_a_real_terminal(capsys, monkeypatch):
    # PrintConsole (what the CLI/REPL actually use) must redraw a live
    # dashboard (sysmon.js, cockpit.js) in place on a real terminal, or it
    # just scrolls a new frame each tick instead. It must NOT do that via
    # `\x1b[2J\x1b[H` (erase the *entire visible terminal*, jump to its
    # absolute top-left) -- that blanks the whole screen for a moment
    # every tick, which is a visible flash, and repaints from the
    # terminal's origin rather than the dashboard's own position,
    # disturbing whatever a shell/REPL printed above it. Instead: move the
    # cursor back up to exactly where the previous frame started (one row,
    # here -- "frame 1" is one line), then erase only from there down.
    from myjs._engine import PrintConsole
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    s = Session(console=PrintConsole())
    s.eval("console.log('frame 1'); console.clear(); console.log('frame 2');")
    out = capsys.readouterr().out
    assert "\x1b[2J" not in out
    assert "\x1b[1F\x1b[J" in out
    assert s.console_lines == ["frame 2"]   # the buffer itself still just clears


def test_console_clear_counts_embedded_newlines_and_wrapped_rows(capsys, monkeypatch):
    # a single `console.log("a\nb")` call prints two real terminal rows, and
    # a line wider than the terminal wraps onto more than one -- both have
    # to be counted, or the cursor is moved up too few rows on the next
    # `clear()` and stale content from the wider/taller previous frame is
    # left behind instead of erased.
    import os as _os
    from myjs._engine import PrintConsole
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback=(80, 24): _os.terminal_size((10, 24)))
    s = Session(console=PrintConsole())
    # a 21-column line wraps to 3 rows at a 10-column width, plus a second
    # (embedded-newline) line of 1 more -> 4 rows total for one log() call.
    s.eval("console.log('0123456789' + '0123456789X' + '\\n' + 'y');")
    s.eval("console.clear();")
    out = capsys.readouterr().out
    assert "\x1b[4F\x1b[J" in out



def test_console_clear_is_silent_when_piped(capsys, monkeypatch):
    from myjs._engine import PrintConsole
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    s = Session(console=PrintConsole())
    s.eval("console.log('frame 1'); console.clear(); console.log('frame 2');")
    out = capsys.readouterr().out
    assert "\x1b[" not in out


def test_console_error_goes_to_stderr(capsys):
    from myjs.cli import main
    main(["-e", "console.log('out'); console.error('err'); console.assert(false, 'bad')"])
    cap = capsys.readouterr()
    assert "out" in cap.out and "err" not in cap.out
    assert "err" in cap.err and "Assertion failed: bad" in cap.err


def test_console_methods_return_undefined():
    s = Session()
    assert s.eval("typeof console.log('x')") == "undefined"
    assert s.eval("[1, 2].forEach(() => {})") is None   # forEach -> undefined


# -- repl -----------------------------------------------------------------

def test_repl_runs_and_displays(capsys, monkeypatch):
    import myjs.repl as replmod
    lines = iter(["1 + 2", "const xs = [1,2,3].map(n => n*n)", "xs",
                  "typeof undefined", "function f(){}", "f", ".exit"])
    monkeypatch.setattr("builtins.input", lambda *a: next(lines))
    monkeypatch.setattr("sys.stdin", type("S", (), {"isatty": staticmethod(lambda: False)})())
    assert replmod.repl(Session()) == 0
    out = capsys.readouterr().out.splitlines()
    assert "3" in out
    assert "undefined" in out                # the declaration
    assert "[ 1, 4, 9 ]" in out
    assert "'undefined'" in out              # typeof result is a string
    assert "[Function: f]" in out


def test_repl_multiline_and_load(tmp_path, capsys, monkeypatch):
    import myjs.repl as replmod
    (tmp_path / "s.js").write_text("globalThis.loaded = 41;\n")
    lines = iter([
        "function add(a,",         # incomplete -> continues
        "  b) { return a + b; }",
        "add(1, 2)",
        f".load {tmp_path / 's.js'}",
        "loaded + 1",
        ".exit",
    ])
    monkeypatch.setattr("builtins.input", lambda *a: next(lines))
    monkeypatch.setattr("sys.stdin", type("S", (), {"isatty": staticmethod(lambda: False)})())
    replmod.repl(Session())
    out = capsys.readouterr().out
    assert "3" in out and "(loaded" in out and "42" in out


def test_display_pretty_prints_nested_values(monkeypatch):
    from myjs.repl import _display

    monkeypatch.setattr("sys.stdout.isatty", lambda: False)  # no ANSI color noise
    s = Session()

    # small/flat -> stays one line, Node-style spacing
    assert _display(s.eval("({a: 1, b: 2})")) == "{ a: 1, b: 2 }"
    assert _display(s.eval("[1, 2, 3]")) == "[ 1, 2, 3 ]"

    # big/nested -> wraps into indented multi-line form
    big = _display(s.eval(
        '({name: "widget", tags: ["a","b","c"], meta: {sku: "XYZ-123", inStock: true}})'
    ))
    assert big.splitlines()[0] == "{"
    assert "  name: 'widget'," in big
    assert "  meta: { sku: 'XYZ-123', inStock: true }" in big

    # a cycle doesn't recurse forever
    assert _display(s.eval("const o = {}; o.self = o; o")) == "{ self: [Circular] }"


def test_display_shows_map_set_regexp_date_symbol_like_a_real_repl(monkeypatch):
    # these used to fall all the way through to the generic `_stringify`
    # fallback -- a regex literal lost its `/.../flags` notation entirely
    # (`/abc/gi` displayed as bare `abc`), Map/Set printed as a raw Python
    # `str(self.args)` indistinguishable from a plain array, a Date showed
    # a Python-`datetime`-style rendering, and a Symbol displayed as the
    # quoted internal string `'@@sym:x:1'` used to represent it.
    from myjs.repl import _display

    monkeypatch.setattr("sys.stdout.isatty", lambda: False)  # no ANSI color noise
    s = Session()

    assert _display(s.eval("/abc/gi")) == "/abc/gi"
    assert _display(s.eval("new Set([1, 2, 3])")) == "Set(3) { 1, 2, 3 }"
    # domonic's Map coerces a numeric key to its string form internally
    # (a real, separate wrinkle -- `.get(1)` and `.get("1")` both hit the
    # same entry, unlike real JS); `_display` just shows whatever the key
    # actually comes back as, faithfully.
    assert _display(s.eval("new Map([[1, 'a']])")) == "Map(1) { '1' => 'a' }"
    assert _display(s.eval("new Set([])")) == "Set(0) {}"
    assert _display(s.eval("new Date(2020, 0, 1)")) == "2020-01-01T00:00:00.000Z"
    assert _display(s.eval("Symbol('x')")) == "Symbol(x)"
    assert _display(s.eval("Symbol()")) == "Symbol()"


def test_display_shows_a_promises_settled_value_like_node(monkeypatch):
    # `_Promise.__repr__` (shared with real coercion, e.g. `String(p)`,
    # which per spec must not leak the settled value) always shows just
    # `Promise { <fulfilled> }` with no value -- a real REPL's inspect
    # shows the settled value itself, the same way Node does.
    from myjs.repl import _display

    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    s = Session()
    assert _display(s.eval("Promise.resolve(42)")) == "Promise { 42 }"
    assert _display(s.eval("new Promise(() => {})")) == "Promise { <pending> }"
    assert _display(s.eval("Promise.resolve({a: 1})")) == "Promise { { a: 1 } }"


def test_repl_completer():
    from myjs.repl import _completer
    import myjs.repl as r
    s = Session()
    s.eval("const alpha = 1; const alphabet = {a: 1, bcd: 2};")
    comp = _completer(s)
    r._readline_buffer = lambda: "alph"
    r._readline_point = lambda: 4
    got = {comp("alph", i) for i in range(5)} - {None}
    assert got == {"alpha", "alphabet"}
    r._readline_buffer = lambda: "alphabet.b"
    r._readline_point = lambda: 10
    assert comp("b", 0) == "alphabet.bcd"


def test_cli_renders_html_file(tmp_path, capsys):
    f = tmp_path / "p.html"
    f.write_text("<!doctype html><html><body><b id=o></b>"
                 "<script>document.getElementById('o').textContent = 2 + 3;</script></body></html>")
    assert main([str(f)]) == 0
    assert "<b id=\"o\">5</b>" in capsys.readouterr().out


def test_cli_html_with_eval_extracts(tmp_path, capsys):
    f = tmp_path / "p.html"
    f.write_text("<!doctype html><html><body><span class=v>7</span>"
                 "<script>document.querySelector('.v').textContent = 42;</script></body></html>")
    assert main([str(f), "-e", "document.querySelector('.v').textContent"]) == 0
    assert capsys.readouterr().out.strip() == "42"


# -- cli ------------------------------------------------------------------

def test_cli_eval(capsys):
    assert main(["-e", "6 * 7"]) == 0
    assert capsys.readouterr().out.strip() == "42"


def test_cli_runs_a_file(tmp_path, capsys):
    f = tmp_path / "s.js"
    f.write_text("console.log('hello', 1 + 1);\n")
    assert main([str(f)]) == 0
    assert "hello 2" in capsys.readouterr().out


def test_cli_reports_js_error(tmp_path, capsys):
    f = tmp_path / "bad.js"
    f.write_text("throw new TypeError('boom');\n")
    assert main([str(f)]) == 1
    assert "TypeError: boom" in capsys.readouterr().err


def test_cli_missing_file(capsys):
    assert main(["/no/such/file.js"]) == 1
    assert "cannot open" in capsys.readouterr().err
