from domonic.events import Event
from domonic.html import main

from domonic_libs import App


class Window:
    def __init__(self):
        self.js = []

    def evaluate_js(self, code, callback=None):
        self.js.append(code)
        return code


def test_menu_item_passes_domonic_menu_event_and_refreshes():
    app = App("Menus")
    app.window = Window()
    seen = []

    @app.route("/")
    def index():
        return main("ok")

    def callback(event):
        seen.append((type(event), event.type))

    item = app.menu_item("Thing", callback)
    item.function()

    assert seen == [(Event, "menu")]
    assert app.window.js[-1].startswith("document.body.innerHTML = ")


def test_menu_item_can_skip_refresh():
    app = App("Menus")
    app.window = Window()
    called = []

    item = app.menu_item("Thing", lambda: called.append(True), refresh=False)
    item.function()

    assert called == [True]
    assert app.window.js == []


def test_menu_adds_pywebview_menu():
    app = App("Menus")
    item = app.menu_item("New", lambda: None, refresh=False)
    menu = app.menu("File", item, app.menu_separator())

    assert menu.title == "File"
    assert [type(item).__name__ for item in app._menus[0].items] == [
        "MenuAction",
        "MenuSeparator",
    ]


def test_submenu_does_not_add_top_level_menu():
    app = App("Menus")
    item = app.menu_item("Thing", lambda: None, refresh=False)
    submenu = app.submenu("Nested", item)

    assert submenu.title == "Nested"
    assert app._menus == []


def test_menu_callback_errors_render_error_view():
    app = App("Menus")
    app.window = Window()

    def fail():
        raise ValueError("menu broke")

    item = app.menu_item("Fail", fail)
    response = item.function()

    assert response["error"]["message"] == "ValueError: menu broke"
    assert "Callback error" in app.window.js[-1]
