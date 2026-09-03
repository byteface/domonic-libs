from __future__ import annotations

from urllib.parse import unquote

from .events import Event, namespace

try:
    from webview.dom import _dnd_state
except Exception:  # pragma: no cover - depends on pywebview internals
    _dnd_state = None


def enable_native_file_drop():
    if _dnd_state is None:
        return

    _dnd_state["num_listeners"] += 1


def merge_native_file_paths(files: list[dict] | None):
    merged = [dict(file) for file in files or []]

    if _dnd_state is None:
        return merged

    paths = list(_dnd_state.get("paths", []))

    for file in merged:
        name = unquote(str(file.get("name", "")))

        for item in paths:
            native_name, native_path = item

            if unquote(native_name) != name:
                continue

            path = unquote(native_path)
            file["path"] = path
            file["pywebviewFullPath"] = path
            _dnd_state["paths"].remove(item)
            paths.remove(item)
            break

    return merged


def file_drop_event(files: list[dict] | None):
    event = Event("drop", {})
    event.files = namespace(merge_native_file_paths(files))
    return event
