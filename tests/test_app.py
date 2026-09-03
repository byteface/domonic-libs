import json
import threading
import time
import urllib.request
from pathlib import Path

from domonic.events import Event, MouseEvent
from domonic.html import button, main

from domonic_libs import App
from domonic_libs.app import BaseApp, BrowserApp, DesktopApp, on
from examples.signature import write_png


def test_package_exports_content_helpers():
    import domonic_libs

    assert domonic_libs.Readability.__name__ == "Readability"
    assert domonic_libs.TurndownService.__name__ == "TurndownService"
    assert domonic_libs.DOMPurify.__name__ == "DOMPurify"
    assert callable(domonic_libs.turndown)
    assert callable(domonic_libs.sanitize)


class Window:
    def __init__(self):
        self.js = []
        self.dialog_result = ()

    def evaluate_js(self, code, callback=None):
        self.js.append((code, callback))
        return code

    def create_file_dialog(self, *args, **kwargs):
        return self.dialog_result


def test_add_event_listener_binds_to_bridge():
    app = App("Test")
    calls = []

    node = button("Go", _id="go")
    node.addEventListener(
        Event.CLICK,
        lambda event: calls.append((type(event), event.target.id)),
    )

    @app.route("/")
    def index():
        return main("ok")

    app._bind_python_events(node)
    response = app._bridge.dispatch(
        "h1",
        {
            "type": Event.CLICK,
            "target": {"id": "go"},
        },
    )

    assert node.kwargs["_onclick"].startswith("return window.__domonicUI.dispatch")
    assert calls == [(MouseEvent, "go")]
    assert "<main>ok</main>" in response["html"]


def test_callback_returning_false_skips_render():
    app = App("Test")

    @app.route("/")
    def index():
        node = button("Go")
        node.addEventListener(Event.CLICK, lambda event: False)
        return main(node)

    app._render_route("/")
    response = app._bridge.dispatch("h1", {"type": Event.CLICK, "target": {}})

    assert response == {}


def test_callback_error_returns_error_view():
    app = App("Test")

    def fail(event):
        raise ValueError("boom")

    @app.route("/")
    def index():
        node = button("Fail")
        node.addEventListener(Event.CLICK, fail)
        return main(node)

    app._render_route("/")
    response = app._bridge.dispatch("h1", {"type": Event.CLICK, "target": {}})

    assert "Callback error" in response["html"]
    assert "ValueError: boom" in response["html"]
    assert response["error"]["message"] == "ValueError: boom"


def test_json_storage_round_trip(tmp_path):
    app = App("Storage", data_dir=tmp_path)

    saved = app.save_json("settings.json", {"ok": True})

    assert saved == tmp_path / "settings.json"
    assert app.load_json("settings.json") == {"ok": True}
    assert app.load_json("missing.json", default={}) == {}


def test_text_storage_and_data_files(tmp_path):
    app = App("Storage", data_dir=tmp_path)

    saved = app.save_text("notes/one.txt", "hello")

    assert saved == tmp_path / "notes" / "one.txt"
    assert app.load_text("notes/one.txt") == "hello"
    assert app.load_text("missing.txt", default="empty") == "empty"
    assert app.data_files("notes/*.txt") == [tmp_path / "notes" / "one.txt"]


def test_window_options_are_stored():
    app = App(
        "Window",
        transparent=True,
        background_color="#000000",
        frameless=True,
        vibrancy=True,
        text_select=True,
    )

    assert app.transparent is True
    assert app.background_color == "#000000"
    assert app.frameless is True
    assert app.vibrancy is True
    assert app.text_select is True


def test_background_color_must_be_hex_triplet():
    try:
        App("Window", background_color="#00000000")
    except ValueError as error:
        assert "6-digit hex color" in str(error)
    else:
        raise AssertionError("background_color should reject alpha hex values")


def test_refresh_replaces_body_html():
    app = App("Refresh")
    app.window = Window()

    @app.route("/")
    def index():
        return main("Hello")

    app.refresh()

    assert app.window.js
    assert app.window.js[-1][0].startswith("document.body.innerHTML = ")
    assert "<main>Hello</main>" in app.window.js[-1][0]


def test_editor_commands_do_not_auto_refresh():
    app = App("Editor")
    app.window = Window()

    assert app.cut() is False
    assert app.copy() is False
    assert app.paste() is False
    assert app.select_all() is False
    assert [item[0] for item in app.window.js] == [
        'document.execCommand("cut")',
        'document.execCommand("copy")',
        'document.execCommand("paste")',
        'document.execCommand("selectAll")',
    ]


def test_evaluate_js_forwards_callback():
    app = App("JS")
    app.window = Window()

    def done(value):
        return value

    app.evaluate_js("Promise.resolve(1)", callback=done)

    assert app.window.js == [("Promise.resolve(1)", done)]


def test_timer_tick_renders_route():
    app = App("Timer")
    state = {"ticks": 0}

    def tick():
        state["ticks"] += 1

    @app.route("/")
    def index():
        return main(str(state["ticks"]))

    timer_id = app.every(1, tick)
    response = app._bridge.tick(timer_id)

    assert state["ticks"] == 1
    assert "<main>1</main>" in response["html"]


def test_file_drop_dispatches_domonic_drop_event():
    app = App("Files")
    seen = []

    @app.route("/")
    def index():
        return main("dropped")

    @app.on_file_drop
    def dropped(event):
        seen.append((event.type, event.files[0].name, event.files[0].size))

    response = app._bridge.file_drop(
        [
            {
                "name": "notes.txt",
                "size": 12,
                "type": "text/plain",
            }
        ]
    )

    assert seen == [("drop", "notes.txt", 12)]
    assert "<main>dropped</main>" in response["html"]


def test_file_drop_callback_returning_false_skips_render():
    app = App("Files")

    @app.on_file_drop
    def dropped(event):
        return False

    assert app._bridge.file_drop([]) == {}


def test_file_dialog_wrappers_require_window(tmp_path):
    app = App("Files")

    try:
        app.open_file()
    except RuntimeError as error:
        assert "window is not running" in str(error)
    else:
        raise AssertionError("open_file should require a running window")

    app.window = Window()
    app.window.dialog_result = (str(Path(tmp_path) / "file.txt"),)

    assert app.open_file() == app.window.dialog_result


def test_app_is_desktop_app_over_shared_base():
    assert App is DesktopApp
    assert issubclass(DesktopApp, BaseApp)
    assert issubclass(BrowserApp, BaseApp)


def test_browser_app_injects_fetch_transport():
    app = BrowserApp("Web")

    @app.route("/")
    def index():
        return main("hi")

    doc = str(app._build_document())
    assert "__domonicUI" in doc  # shared client runtime
    assert "/__domonic/" in doc  # fetch transport bootstrap
    assert "DOMContentLoaded" in doc  # browser ready event, not pywebviewready


def test_browser_app_evaluate_js_queues_command():
    app = BrowserApp("Web")
    app.evaluate_js("console.log(1)")
    drained = app._drain_commands()
    assert drained == [{"op": "eval", "code": "console.log(1)"}]
    assert app._drain_commands() == []


def test_browser_app_serves_and_dispatches():
    app = BrowserApp("Web")
    clicks = {"n": 0}

    @app.route("/")
    def index():
        return main(
            f"count: {clicks['n']}",
            on(button("inc", _id="b"), Event.CLICK, lambda e: clicks.__setitem__("n", clicks["n"] + 1)),
        )

    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=8749, open_browser=False),
        daemon=True,
    )
    thread.start()
    try:
        time.sleep(0.5)
        page = urllib.request.urlopen("http://127.0.0.1:8749/").read().decode()
        assert "count: 0" in page

        import re

        handler_id = re.search(r"dispatch\(event, '(h\d+)'\)", page).group(1)
        request = urllib.request.Request(
            "http://127.0.0.1:8749/__domonic/dispatch",
            data=json.dumps([handler_id, {"type": "click", "target": {"id": "b"}}]).encode(),
            headers={"Content-Type": "application/json"},
        )
        response = json.loads(urllib.request.urlopen(request).read())
        assert "count: 1" in response["html"]
        assert clicks["n"] == 1
    finally:
        if app._server is not None:
            app._server.shutdown()


def test_signature_write_png_adds_extension(tmp_path):
    data_url = "data:image/png;base64,iVBORw0KGgo="
    path = tmp_path / "signature"

    write_png(path, data_url)

    assert (tmp_path / "signature.png").read_bytes() == b"\x89PNG\r\n\x1a\n"
