from __future__ import annotations

from datetime import datetime
import hashlib
import mimetypes
import os
from pathlib import Path
import stat

from domonic.events import Event
from domonic.html import (
    button,
    code,
    div,
    form,
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

try:
    import grp
    import pwd
except ImportError:  # pragma: no cover - Windows fallback
    grp = None
    pwd = None


NOTES_FILE = "file-info-notes.json"
MAX_HASH_BYTES = 50 * 1024 * 1024

app = App("File Info", width=980, height=720, debug=False)

state = {
    "file": None,
    "draft_name": "",
    "draft_notes": "",
    "draft_tags": "",
    "readonly": False,
    "status": "Drop a file here, or choose one from disk.",
}
notes_store = app.load_json(NOTES_FILE, default={}) or {}


def format_bytes(size):
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)

    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def format_time(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def owner_name(stat_result):
    if pwd is None:
        return str(stat_result.st_uid)

    try:
        return pwd.getpwuid(stat_result.st_uid).pw_name
    except KeyError:
        return str(stat_result.st_uid)


def group_name(stat_result):
    if grp is None:
        return str(stat_result.st_gid)

    try:
        return grp.getgrgid(stat_result.st_gid).gr_name
    except KeyError:
        return str(stat_result.st_gid)


def sha256_for(path, stat_result):
    if not path.is_file():
        return "Folders are not hashed"

    if stat_result.st_size > MAX_HASH_BYTES:
        return f"Skipped over {format_bytes(MAX_HASH_BYTES)}"

    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def sidecar_for(path):
    return notes_store.get(str(path), {"notes": "", "tags": ""})


def inspect_path(path):
    path = Path(path).expanduser()

    if not path.exists():
        state["status"] = f"Not found: {path}"
        return

    stat_result = path.lstat()
    mime_type, encoding = mimetypes.guess_type(path.name)
    mode = stat_result.st_mode
    sidecar = sidecar_for(path)

    state["file"] = {
        "path": str(path),
        "name": path.name,
        "parent": str(path.parent),
        "kind": "Folder" if path.is_dir() else "File",
        "extension": path.suffix or "None",
        "mime": mime_type or "Unknown",
        "encoding": encoding or "None",
        "size": stat_result.st_size,
        "size_label": format_bytes(stat_result.st_size),
        "created": format_time(getattr(stat_result, "st_birthtime", stat_result.st_ctime)),
        "modified": format_time(stat_result.st_mtime),
        "accessed": format_time(stat_result.st_atime),
        "permissions": stat.filemode(mode),
        "mode": oct(stat.S_IMODE(mode)),
        "owner": owner_name(stat_result),
        "group": group_name(stat_result),
        "readonly": not os.access(path, os.W_OK),
        "symlink": path.is_symlink(),
        "sha256": sha256_for(path, stat_result),
        "drop_path": True,
    }
    state["draft_name"] = path.name
    state["draft_notes"] = sidecar.get("notes", "")
    state["draft_tags"] = sidecar.get("tags", "")
    state["readonly"] = state["file"]["readonly"]
    state["status"] = f"Loaded {path.name}"


def inspect_browser_file(file):
    state["file"] = {
        "path": "",
        "name": getattr(file, "name", "Unknown"),
        "parent": "Unavailable from browser drop",
        "kind": "Dropped browser file",
        "extension": Path(getattr(file, "name", "")).suffix or "None",
        "mime": getattr(file, "type", "") or "Unknown",
        "encoding": "None",
        "size": getattr(file, "size", 0),
        "size_label": format_bytes(getattr(file, "size", 0)),
        "created": "Unavailable",
        "modified": (
            datetime.fromtimestamp(file.lastModified / 1000).strftime("%Y-%m-%d %H:%M:%S")
            if getattr(file, "lastModified", None)
            else "Unavailable"
        ),
        "accessed": "Unavailable",
        "permissions": "Unavailable",
        "mode": "Unavailable",
        "owner": "Unavailable",
        "group": "Unavailable",
        "readonly": False,
        "symlink": False,
        "sha256": "Use Choose File for filesystem access",
        "drop_path": False,
    }
    state["draft_name"] = state["file"]["name"]
    state["draft_notes"] = ""
    state["draft_tags"] = ""
    state["readonly"] = False
    state["status"] = "Drop worked, but this webview did not expose a full path."


def choose_file(event=None):
    paths = app.open_file(
        file_types=(
            "All files (*.*)",
        )
    )
    path = paths[0] if isinstance(paths, (list, tuple)) and paths else paths

    if path:
        inspect_path(path)
    else:
        state["status"] = "Choose file canceled"


def handle_drop(event):
    files = getattr(event, "files", []) or []

    if not files:
        state["status"] = "Nothing was dropped"
        return

    file = files[0]
    path = getattr(file, "path", "") or getattr(file, "pywebviewFullPath", "")

    if path and Path(path).exists():
        inspect_path(path)
        return

    inspect_browser_file(file)


def update_name(event):
    state["draft_name"] = event.value or ""
    return False


def update_notes(event):
    state["draft_notes"] = event.value or ""
    return False


def update_tags(event):
    state["draft_tags"] = event.value or ""
    return False


def toggle_readonly(event):
    state["readonly"] = bool(getattr(event, "checked", False))


def save_metadata(event):
    info = state["file"]

    if not info or not info.get("path"):
        state["status"] = "Use Choose File first before editing metadata."
        return

    path = Path(info["path"])
    new_name = state["draft_name"].strip() or path.name

    if new_name != path.name:
        new_path = path.with_name(new_name)

        if new_path.exists():
            state["status"] = f"Cannot rename: {new_name} already exists"
            return

        path.rename(new_path)
        path = new_path

    mode = path.stat().st_mode

    if state["readonly"]:
        os.chmod(path, mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
    else:
        os.chmod(path, mode | stat.S_IWUSR)

    notes_store[str(path)] = {
        "notes": state["draft_notes"],
        "tags": state["draft_tags"],
    }
    app.save_json(NOTES_FILE, notes_store)
    inspect_path(path)
    state["status"] = f"Saved metadata for {path.name}"


def info_row(label_text, value):
    return li(span(label_text, _class="label"), code(str(value)))


def action_button(label_text, callback, class_name=""):
    attrs = {"_type": "button"}

    if class_name:
        attrs["_class"] = class_name

    return on(button(label_text, **attrs), Event.CLICK, callback)


app.on_file_drop(handle_drop)
app.menu(
    "File",
    app.menu_item("Choose File...", choose_file),
    app.menu_item("Save Metadata", save_metadata),
)
app.menu(
    "Edit",
    app.menu_item("Cut", app.cut),
    app.menu_item("Copy", app.copy),
    app.menu_item("Paste", app.paste),
    app.menu_separator(),
    app.menu_item("Select All", app.select_all),
)


@app.route("/")
def index():
    info = state["file"]

    return main(
        style(
            """
            :root {
                color-scheme: light;
            }

            body {
                margin: 0;
                padding: 0;
                background: #f4f5f7;
                color: #1f2328;
            }

            main {
                min-height: 100vh;
                display: grid;
                grid-template-rows: auto 1fr;
                gap: 18px;
                padding: 22px;
                box-sizing: border-box;
            }

            .drop-zone {
                border: 2px dashed #6b7280;
                border-radius: 8px;
                background: #ffffff;
                padding: 20px;
                display: grid;
                grid-template-columns: minmax(0, 1fr) auto;
                gap: 16px;
                align-items: center;
            }

            body.domonic-libs-dragging .drop-zone {
                border-color: #0f766e;
                background: #ecfdf5;
            }

            h1, h2, p {
                margin: 0;
            }

            h1 {
                font-size: 24px;
            }

            h2 {
                font-size: 15px;
                text-transform: uppercase;
                letter-spacing: 0;
                color: #57606a;
            }

            button {
                border: 1px solid #8c959f;
                border-radius: 6px;
                background: #ffffff;
                color: #24292f;
                cursor: pointer;
            }

            button.primary {
                background: #0969da;
                border-color: #0969da;
                color: #ffffff;
            }

            .content {
                display: grid;
                grid-template-columns: minmax(0, 1fr) 320px;
                gap: 18px;
                min-height: 0;
            }

            section {
                min-width: 0;
                background: #ffffff;
                border: 1px solid #d0d7de;
                border-radius: 8px;
                padding: 18px;
                box-sizing: border-box;
            }

            .summary {
                display: grid;
                gap: 10px;
            }

            .summary .name {
                font-size: 28px;
                font-weight: 700;
                overflow-wrap: anywhere;
            }

            .summary .path {
                color: #57606a;
                overflow-wrap: anywhere;
            }

            ul {
                list-style: none;
                margin: 18px 0 0;
                padding: 0;
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 10px;
            }

            li {
                min-width: 0;
                display: grid;
                gap: 4px;
                border-top: 1px solid #d8dee4;
                padding-top: 10px;
            }

            .label {
                color: #57606a;
                font-size: 12px;
                text-transform: uppercase;
            }

            code {
                color: #24292f;
                background: transparent;
                font: 13px ui-monospace, SFMono-Regular, Menlo, monospace;
                white-space: normal;
                overflow-wrap: anywhere;
            }

            form {
                display: grid;
                gap: 14px;
            }

            label {
                display: grid;
                gap: 6px;
                color: #57606a;
                font-size: 13px;
            }

            input, textarea {
                width: 100%;
                box-sizing: border-box;
                border: 1px solid #8c959f;
                border-radius: 6px;
                background: #ffffff;
                color: #1f2328;
                font: inherit;
                padding: 9px 10px;
            }

            textarea {
                min-height: 130px;
                resize: vertical;
            }

            .checkbox {
                display: flex;
                align-items: center;
                gap: 8px;
                color: #24292f;
            }

            .checkbox input {
                width: auto;
            }

            .empty {
                color: #57606a;
                display: grid;
                gap: 10px;
            }

            .status {
                color: #57606a;
                font-size: 13px;
            }

            @media (max-width: 760px) {
                .drop-zone,
                .content {
                    grid-template-columns: 1fr;
                }

                ul {
                    grid-template-columns: 1fr;
                }
            }
            """
        ),
        div(
            div(
                h1("File Info"),
                p(state["status"], _class="status"),
            ),
            action_button("Choose File", choose_file, "primary"),
            _class="drop-zone",
        ),
        div(
            section(
                (
                    div(
                        p(info["name"], _class="name"),
                        p(info["path"] or info["parent"], _class="path"),
                        _class="summary",
                    )
                    if info
                    else div(
                        h2("Waiting"),
                        p("Drop a file from Finder onto this window."),
                        p("If this webview exposes a native path, full filesystem info appears here."),
                        _class="empty",
                    )
                ),
                (
                    ul(
                        info_row("Kind", info["kind"]),
                        info_row("Size", f"{info['size_label']} ({info['size']} bytes)"),
                        info_row("Type", info["mime"]),
                        info_row("Extension", info["extension"]),
                        info_row("Created", info["created"]),
                        info_row("Modified", info["modified"]),
                        info_row("Accessed", info["accessed"]),
                        info_row("Permissions", f"{info['permissions']} / {info['mode']}"),
                        info_row("Owner", info["owner"]),
                        info_row("Group", info["group"]),
                        info_row("Symlink", "Yes" if info["symlink"] else "No"),
                        info_row("SHA-256", info["sha256"]),
                    )
                    if info
                    else ""
                ),
            ),
            section(
                h2("Editable"),
                form(
                    label(
                        "Name",
                        on(
                            input(
                                _name="name",
                                _value=state["draft_name"],
                                _autocomplete="off",
                            ),
                            Event.INPUT,
                            update_name,
                        ),
                    ),
                    label(
                        "Tags",
                        on(
                            input(
                                _name="tags",
                                _value=state["draft_tags"],
                                _autocomplete="off",
                            ),
                            Event.INPUT,
                            update_tags,
                        ),
                    ),
                    label(
                        "Notes",
                        on(
                            textarea(
                                state["draft_notes"],
                                _name="notes",
                                _autocomplete="off",
                                _spellcheck="true",
                            ),
                            Event.INPUT,
                            update_notes,
                        ),
                    ),
                    label(
                        on(
                            input(
                                _type="checkbox",
                                _name="readonly",
                                _checked=state["readonly"],
                            ),
                            Event.CHANGE,
                            toggle_readonly,
                        ),
                        "Read only",
                        _class="checkbox",
                    ),
                    action_button("Save Metadata", save_metadata, "primary"),
                ),
            ),
            _class="content",
        ),
    )


if __name__ == "__main__":
    app.run()
