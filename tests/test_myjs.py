"""The ``myjs`` package: Session API, the ffi bridge, and the CLI."""

import ctypes.util

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


def test_os_namespace_is_node_flavoured():
    s = Session()
    assert s.eval("os.platform()") in ("darwin", "linux", "win32")
    assert s.eval("os.cpus().length") >= 1
    assert s.eval("typeof os.homedir()") == "string"


def test_require_returns_builtins_and_python_modules():
    s = Session()
    assert s.eval("require('fs') === fs") is True
    assert s.eval("require('math').pi > 3.14") is True


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


@pytest.mark.skipif(not ctypes.util.find_library("c"), reason="offline-ish guard")
def test_async_fetch_is_concurrent():
    import time as _t

    s = Session()
    start = _t.time()
    try:
        s.eval(
            "(async () => {"
            "  const rs = await Promise.all(["
            "    fetch('https://httpbin.org/delay/1'),"
            "    fetch('https://httpbin.org/delay/1'),"
            "  ]);"
            "  console.log(rs.map(r => r.status).join(','));"
            "})();"
        )
    except Exception as exc:  # network flake -> skip, don't fail
        pytest.skip(f"network unavailable: {exc}")
    assert s.console_lines == ["200,200"]
    assert _t.time() - start < 1.9  # two 1s requests overlapped


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
