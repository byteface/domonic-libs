from datetime import datetime
from pathlib import Path
import re
from uuid import uuid4

from domonic.events import Event
from domonic.html import (
    aside,
    button,
    div,
    h1,
    h2,
    input,
    label,
    li,
    main,
    p,
    section,
    span,
    style,
    textarea,
    ul,
)

from domonic_libs import App, on


STORE_FILE = "snippets.json"

app = App("Snippet Box", width=980, height=680, debug=False)

state = {
    "snippets": app.load_json(STORE_FILE, default=[]) or [],
    "selected": "",
    "status": "Ready",
}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "snippet"


def save_store():
    app.save_json(STORE_FILE, state["snippets"])
    state["status"] = f"Saved {now()}"


def ensure_snippet():
    if state["snippets"]:
        state["selected"] = state["selected"] or state["snippets"][0]["id"]
        return

    snippet = {
        "id": str(uuid4()),
        "title": "Welcome",
        "body": "Store small notes, commands, or code fragments here.",
        "updated": now(),
    }
    state["snippets"].append(snippet)
    state["selected"] = snippet["id"]
    save_store()


def selected_snippet():
    ensure_snippet()

    for snippet in state["snippets"]:
        if snippet["id"] == state["selected"]:
            return snippet

    state["selected"] = state["snippets"][0]["id"]
    return state["snippets"][0]


def update_snippet(**changes):
    snippet = selected_snippet()
    snippet.update(changes)
    snippet["updated"] = now()
    save_store()


def new_snippet(event):
    snippet = {
        "id": str(uuid4()),
        "title": "Untitled",
        "body": "",
        "updated": now(),
    }
    state["snippets"].insert(0, snippet)
    state["selected"] = snippet["id"]
    save_store()


def delete_snippet(event):
    snippet = selected_snippet()
    state["snippets"] = [
        item for item in state["snippets"] if item["id"] != snippet["id"]
    ]
    state["selected"] = state["snippets"][0]["id"] if state["snippets"] else ""
    save_store()


def select_snippet(event):
    state["selected"] = (
        getattr(event, "value", None)
        or getattr(getattr(event, "currentTarget", None), "value", None)
        or state["selected"]
    )


def update_title(event):
    update_snippet(title=event.value or "Untitled")


def update_body(event):
    update_snippet(body=event.value or "")
    return False


def backup_snippet(event):
    snippet = selected_snippet()
    filename = f"backups/{slugify(snippet['title'])}.txt"
    app.save_text(filename, snippet["body"])
    state["status"] = f"Backed up to {app.data_path(filename)}"


def export_snippet(event):
    snippet = selected_snippet()
    path = app.save_file(
        filename=f"{slugify(snippet['title'])}.txt",
        file_types=(
            "Text files (*.txt;*.md;*.py)",
            "All files (*.*)",
        ),
    )
    path = path[0] if isinstance(path, (list, tuple)) and path else path

    if not path:
        state["status"] = "Export canceled"
        return

    Path(path).write_text(snippet["body"], encoding="utf-8")
    state["status"] = f"Exported {Path(path).name}"


def raise_example_error(event):
    raise RuntimeError("Snippet Box example error")


def snippet_button(snippet):
    classes = ["snippet-button"]

    if snippet["id"] == state["selected"]:
        classes.append("selected")

    node = button(
        span(snippet["title"], _class="snippet-title"),
        span(snippet["updated"], _class="snippet-date"),
        _type="button",
        _value=snippet["id"],
        _class=" ".join(classes),
    )
    return on(node, Event.CLICK, select_snippet)


def action_button(label, callback, class_name=""):
    attrs = {"_type": "button"}

    if class_name:
        attrs["_class"] = class_name

    return on(button(label, **attrs), Event.CLICK, callback)


app.menu(
    "File",
    app.menu_item("New Snippet", new_snippet),
    app.menu_item("Export Selected...", export_snippet),
    app.submenu(
        "Backups",
        app.menu_item("Backup Selected", backup_snippet),
    ),
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
    "Debug",
    app.menu_item("Raise Callback Error", raise_example_error),
)


@app.route("/")
def index():
    snippet = selected_snippet()
    backup_count = len(app.data_files("backups/*.txt"))

    title_input = on(
        input(
            _name="title",
            _value=snippet["title"],
            _autocomplete="off",
        ),
        Event.INPUT,
        update_title,
    )
    body_input = on(
        textarea(
            snippet["body"],
            _name="body",
            _placeholder="Write a snippet.",
            _autocomplete="off",
            _autocorrect="off",
            _spellcheck="false",
        ),
        Event.INPUT,
        update_body,
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
                color: #20242a;
            }

            main {
                height: 100vh;
                display: grid;
                grid-template-columns: 280px minmax(0, 1fr);
                overflow: hidden;
            }

            aside {
                min-width: 0;
                overflow: auto;
                border-right: 1px solid #cbd3dc;
                background: #ffffff;
                padding: 18px;
                box-sizing: border-box;
            }

            section {
                min-width: 0;
                display: grid;
                grid-template-rows: auto auto minmax(0, 1fr) auto;
                gap: 12px;
                overflow: hidden;
                padding: 18px;
                box-sizing: border-box;
            }

            h1,
            h2,
            p,
            ul {
                margin: 0;
            }

            h1 {
                font-size: 18px;
                margin-bottom: 14px;
            }

            h2 {
                font-size: 16px;
            }

            ul {
                display: grid;
                gap: 8px;
                list-style: none;
                padding: 0;
            }

            .snippet-button {
                width: 100%;
                display: grid;
                gap: 4px;
                border: 1px solid #d4dce5;
                border-radius: 8px;
                background: #f8fafc;
                color: #20242a;
                cursor: pointer;
                padding: 10px;
                text-align: left;
            }

            .snippet-button.selected {
                border-color: #22577a;
                box-shadow: inset 0 0 0 2px rgba(34, 87, 122, 0.18);
            }

            .snippet-title {
                overflow: hidden;
                font-weight: 800;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .snippet-date,
            .meta,
            .status {
                color: #66727f;
                font-size: 13px;
            }

            .top {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 14px;
            }

            .actions {
                display: flex;
                gap: 8px;
            }

            button {
                min-height: 36px;
                border: 1px solid #bec8d2;
                border-radius: 6px;
                background: #ffffff;
                color: #20242a;
                cursor: pointer;
                font: inherit;
                font-weight: 700;
                padding: 7px 10px;
            }

            button.primary {
                border-color: #22577a;
                background: #22577a;
                color: white;
            }

            label {
                display: grid;
                gap: 6px;
                min-height: 0;
                color: #374151;
                font-size: 13px;
                font-weight: 800;
            }

            input,
            textarea {
                box-sizing: border-box;
                width: 100%;
                border: 1px solid #c6ced7;
                border-radius: 8px;
                background: #ffffff;
                color: #111827;
                caret-color: #111827;
                font: inherit;
            }

            input {
                min-height: 42px;
                padding: 9px 11px;
            }

            textarea {
                height: 100%;
                min-height: 0;
                padding: 12px;
                font: 15px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
                letter-spacing: 0;
                resize: none;
            }

            .status {
                display: flex;
                justify-content: space-between;
                gap: 16px;
            }

            @media (max-width: 760px) {
                main {
                    height: auto;
                    min-height: 100vh;
                    grid-template-columns: 1fr;
                    overflow: visible;
                }

                section {
                    min-height: 640px;
                }
            }
            """
        ),
        aside(
            h1("Snippet Box"),
            ul(*[li(snippet_button(item)) for item in state["snippets"]]),
            p(f"{len(state['snippets'])} snippets", _class="meta"),
        ),
        section(
            div(
                div(
                    h2(snippet["title"]),
                    p(f"Updated {snippet['updated']}", _class="meta"),
                ),
                div(
                    action_button("New", new_snippet),
                    action_button("Backup", backup_snippet),
                    action_button("Export", export_snippet, "primary"),
                    _class="actions",
                ),
                _class="top",
            ),
            label("Title", title_input),
            label("Body", body_input),
            div(
                span(state["status"]),
                span(f"{backup_count} text backups"),
                _class="status",
            ),
        ),
    )


app.run()
