from pathlib import Path

from domonic.events import Event
from domonic.html import button, div, h1, main, p, section, span, style, textarea

from domonic_libs import App


app = App("Notepad", width=900, height=640, debug=False)

state = {
    "path": "",
    "text": "",
    "dirty": False,
    "status": "New document",
}


def listen(node, event_type, callback):
    node.addEventListener(event_type, callback)
    return node


def first_path(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else ""

    return value or ""


def document_name():
    if state["path"]:
        return Path(state["path"]).name

    return "Untitled"


def new_document(event):
    state.update(
        {
            "path": "",
            "text": "",
            "dirty": False,
            "status": "New document",
        }
    )


def open_document(event):
    path = first_path(
        app.open_file(
            file_types=(
                "Text documents (*.txt;*.md;*.py;*.json;*.csv)",
                "All files (*.*)",
            )
        )
    )

    if not path:
        state["status"] = "Open canceled"
        return

    file_path = Path(path)

    try:
        state["text"] = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        state["status"] = f"{file_path.name} is not UTF-8 text"
        return
    except OSError as error:
        state["status"] = f"Could not open {file_path.name}: {error}"
        return

    state["path"] = str(file_path)
    state["dirty"] = False
    state["status"] = f"Opened {file_path.name}"


def save_document(event):
    if not state["path"]:
        return save_document_as(event)

    return write_document(Path(state["path"]))


def save_document_as(event):
    path = first_path(
        app.save_file(
            filename=document_name(),
            file_types=(
                "Text documents (*.txt;*.md)",
                "All files (*.*)",
            ),
        )
    )

    if not path:
        state["status"] = "Save canceled"
        return

    return write_document(Path(path))


def write_document(path):
    try:
        path.write_text(state["text"], encoding="utf-8")
    except OSError as error:
        state["status"] = f"Could not save {path.name}: {error}"
        return

    state["path"] = str(path)
    state["dirty"] = False
    state["status"] = f"Saved {path.name}"


def update_text(event):
    state["text"] = event.value or ""
    state["dirty"] = True
    state["status"] = "Unsaved changes"
    return False


def toolbar_button(label, callback, class_name=""):
    attrs = {"_type": "button"}

    if class_name:
        attrs["_class"] = class_name

    return listen(button(label, **attrs), Event.CLICK, callback)


def menu_about():
    state["status"] = "domonic-libs Notepad"


app.menu(
    "File",
    app.menu_item("New", new_document),
    app.menu_item("Open...", open_document),
    app.menu_separator(),
    app.menu_item("Save", save_document),
    app.menu_item("Save As...", save_document_as),
)
app.menu(
    "Edit",
    app.menu_item("Cut", app.cut),
    app.menu_item("Copy", app.copy),
    app.menu_item("Paste", app.paste),
    app.menu_separator(),
    app.menu_item("Select All", app.select_all),
)
app.menu(
    "Window",
    app.menu_item("Reload", app.refresh, refresh=False),
)
app.menu(
    "Help",
    app.menu_item("About Notepad", menu_about),
)


@app.route("/")
def index():
    editor = listen(
        textarea(
            state["text"],
            _name="document",
            _placeholder="Open a local text file or start typing.",
            _autocomplete="off",
            _autocorrect="off",
            _spellcheck="false",
        ),
        Event.INPUT,
        update_text,
    )

    return main(
        style(
            """
            :root {
                color-scheme: light;
            }

            body {
                margin: 0;
                padding: 0;
                background: #eef2f5;
                color: #1f2328;
            }

            main {
                height: 100vh;
                display: grid;
                grid-template-rows: auto minmax(0, 1fr);
                overflow: hidden;
            }

            .topbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 18px;
                border-bottom: 1px solid #cbd3dc;
                background: #ffffff;
                padding: 14px 18px;
            }

            h1,
            p {
                margin: 0;
            }

            h1 {
                font-size: 17px;
                line-height: 1.2;
            }

            .path {
                display: block;
                max-width: 520px;
                overflow: hidden;
                color: #66727f;
                font-size: 13px;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .toolbar {
                display: flex;
                gap: 8px;
            }

            button {
                min-height: 36px;
                border: 1px solid #bec8d2;
                border-radius: 6px;
                background: #ffffff;
                color: #1f2328;
                cursor: pointer;
                font: inherit;
                font-weight: 700;
                padding: 7px 11px;
            }

            button.primary {
                border-color: #22577a;
                background: #22577a;
                color: white;
            }

            .editor {
                min-height: 0;
                display: grid;
                grid-template-rows: minmax(0, 1fr) auto;
                padding: 16px;
                box-sizing: border-box;
            }

            textarea {
                box-sizing: border-box;
                width: 100%;
                height: 100%;
                min-height: 0;
                border: 1px solid #cbd3dc;
                border-radius: 8px;
                background: #ffffff;
                color: #111827;
                caret-color: #111827;
                font: 15px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
                letter-spacing: 0;
                padding: 14px;
                resize: none;
            }

            .status {
                display: flex;
                justify-content: space-between;
                gap: 18px;
                min-height: 28px;
                padding-top: 10px;
                color: #66727f;
                font-size: 13px;
            }

            @media (max-width: 700px) {
                .topbar {
                    display: grid;
                }

                .toolbar {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                }

                .path {
                    max-width: 100%;
                }
            }
            """
        ),
        section(
            div(
                h1(document_name()),
                span(state["path"] or "No file selected", _class="path"),
            ),
            div(
                toolbar_button("New", new_document),
                toolbar_button("Open", open_document),
                toolbar_button("Save", save_document, "primary"),
                toolbar_button("Save As", save_document_as),
                _class="toolbar",
            ),
            _class="topbar",
        ),
        section(
            editor,
            div(
                span(state["status"]),
                span("Unsaved" if state["dirty"] else "Saved"),
                _class="status",
            ),
            _class="editor",
        ),
    )


app.run()
