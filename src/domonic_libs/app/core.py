"""``BaseApp`` -- the host-agnostic core of the domonic-libs app framework.

The render loop is the same everywhere: a route view returns a domonic tree,
``_bind_python_events`` walks it and swaps every ``_on*`` handler /
``addEventListener`` listener for an ``onclick="window.__domonicUI.dispatch(...)"``
string (stashing the Python callback by id), the tree is serialised, a client
runtime (``client.CLIENT_SCRIPT``) drives it, and every interaction round-trips
through ``Bridge`` and comes back as a fresh render the client applies.

Only the *transport* -- how the ``Bridge`` methods are reached from the client,
and how out-of-band messages get back -- and the *native host* -- window chrome,
menus, dialogs -- vary. Those live in ``DesktopApp`` (pywebview) and
``BrowserApp`` (a stdlib HTTP server). ``BaseApp`` knows neither.
"""

from __future__ import annotations

from itertools import count
from pathlib import Path
from typing import Any, Callable

from domonic.html import body, div, h1, head, html, meta, p, pre, script, style, title

from .bridge import Bridge
from .client import CLIENT_SCRIPT
from .events import BROWSER_EVENTS
from .storage import (
    default_data_dir,
    list_files,
    load_json,
    load_text,
    save_json,
    save_text,
)

EventHandler = Callable[[Any], Any]


class BaseApp:
    #: The client event that signals the runtime is ready to accept
    #: ``__domonicUI`` calls. pywebview fires ``pywebviewready``; a plain browser
    #: uses ``DOMContentLoaded``.
    client_ready_event = "pywebviewready"

    def __init__(
        self,
        title: str,
        *,
        data_dir: str | Path | None = None,
        debug: bool = False,
    ):
        self.title = title
        self.debug = debug
        self.data_dir = Path(data_dir) if data_dir else default_data_dir(title)

        self._routes: dict[str, Callable[[], Any]] = {}
        self._handlers: dict[str, EventHandler] = {}
        self._handler_ids = count(1)
        self._timers: dict[str, Callable[[], Any]] = {}
        self._timer_intervals: dict[str, int] = {}
        self._timer_ids = count(1)
        self._file_drop_handlers: list[EventHandler] = []
        self._menus: list[Any] = []
        self._bridge = Bridge(self)
        self._last_error: dict[str, str] | None = None

    # -- routing -----------------------------------------------------------

    def route(self, path: str):
        def decorator(view: Callable[[], Any]):
            self._routes[path] = view
            return view

        return decorator

    # -- storage ---------------------------------------------------------------

    def data_path(self, *parts: str):
        return self.data_dir.joinpath(*parts)

    def load_json(self, filename: str, default: Any = None):
        return load_json(self.data_path(filename), default=default)

    def save_json(self, filename: str, data: Any):
        return save_json(self.data_path(filename), data)

    def load_text(self, filename: str, default: str = "", *, encoding: str = "utf-8"):
        return load_text(self.data_path(filename), default=default, encoding=encoding)

    def save_text(self, filename: str, text: str, *, encoding: str = "utf-8"):
        return save_text(self.data_path(filename), text, encoding=encoding)

    def data_files(self, pattern: str = "*"):
        return list_files(self.data_dir, pattern)

    # -- timers / file drop --------------------------------------------------

    def every(self, interval: float, callback: Callable[[], Any]):
        timer_id = f"t{next(self._timer_ids)}"
        self._timers[timer_id] = callback
        self._timer_intervals[timer_id] = int(
            interval * 1000 if interval < 60 else interval
        )
        return timer_id

    def on_file_drop(self, callback: EventHandler):
        self._file_drop_handlers.append(callback)
        return callback

    # -- host hooks (overridden by DesktopApp / BrowserApp) -----------------

    def run(self):
        raise NotImplementedError("Use DesktopApp or BrowserApp, or App().")

    def evaluate_js(self, code: str, callback: Callable[..., Any] | None = None):
        raise NotImplementedError

    def refresh(self, path: str = "/"):
        raise NotImplementedError

    def _client_bootstrap(self) -> str:
        """Extra JS injected right after ``CLIENT_SCRIPT`` (e.g. a transport)."""
        return ""

    def _drain_commands(self) -> list[dict]:
        """Client commands to attach to the next response (BrowserApp only)."""
        return []

    # -- render loop -------------------------------------------------------

    def _build_document(self):
        return html(
            head(
                meta(_charset="utf-8"),
                meta(
                    _name="viewport",
                    _content="width=device-width, initial-scale=1",
                ),
                title(self.title),
                style(self._base_css()),
                script(CLIENT_SCRIPT),
                script(self._client_bootstrap()),
            ),
            body(
                self._render_tree("/"),
                script(self._file_drop_script()),
                script(self._timer_script()),
            ),
        )

    def _bind_python_events(self, node: Any):
        kwargs = getattr(node, "kwargs", None)

        if isinstance(kwargs, dict):
            listener_callbacks: dict[str, list[EventHandler]] = {}

            for event_type, callbacks in getattr(node, "listeners", {}).items():
                if event_type in BROWSER_EVENTS:
                    listener_callbacks[event_type] = list(callbacks)

            for attribute, value in list(kwargs.items()):
                if not attribute.startswith("_on"):
                    continue

                if not callable(value):
                    continue

                event_type = attribute[3:].lower()
                listener_callbacks.setdefault(event_type, []).append(value)

            for event_type, callbacks in listener_callbacks.items():
                handler_id = f"h{next(self._handler_ids)}"
                self._handlers[handler_id] = self._event_handler(callbacks)
                attribute = f"_on{event_type.lower()}"
                kwargs[attribute] = (
                    "return window.__domonicUI.dispatch("
                    f"event, '{handler_id}'"
                    ")"
                )

        for child in getattr(node, "args", ()):
            if hasattr(child, "args"):
                self._bind_python_events(child)

    def _render_route(self, path: str):
        return str(self._render_tree(path))

    def _render_tree(self, path: str):
        if self._last_error is not None:
            return self._error_view(self._last_error)

        view = self._routes.get(path)

        if view is None:
            raise RuntimeError(
                f'No view registered for "{path}". Add @app.route("{path}").'
            )

        self._handlers.clear()
        self._handler_ids = count(1)

        tree = view()
        self._bind_python_events(tree)
        return tree

    def _event_handler(self, callbacks: list[EventHandler]):
        def handler(event):
            should_render = True

            for callback in callbacks:
                if callback(event) is False:
                    should_render = False

            return should_render

        return handler

    def _timer_script(self):
        lines = [f"window.addEventListener('{self.client_ready_event}', function () {{"]
        for timer_id in self._timers:
            lines.append(
                "window.__domonicUI.startTimer("
                f"'{timer_id}', {self._timer_interval(timer_id)}"
                ");"
            )
        lines.append("});")
        return "\n".join(lines)

    def _file_drop_script(self):
        if not self._file_drop_handlers:
            return ""

        return (
            f"window.addEventListener('{self.client_ready_event}', function () {{"
            "window.__domonicUI.startFileDrop();"
            "});"
        )

    def _timer_interval(self, timer_id: str):
        return self._timer_intervals[timer_id]

    def _dispatch_file_drop(self, event):
        should_render = True

        for callback in self._file_drop_handlers:
            if callback(event) is False:
                should_render = False

        return should_render

    def _handle_callback_error(self, error: Exception, traceback_text: str):
        self._last_error = {
            "message": f"{type(error).__name__}: {error}",
            "traceback": traceback_text,
        }
        return {
            "html": self._render_route("/"),
            "error": self._last_error,
        }

    def _error_view(self, error: dict[str, str]):
        return div(
            style(
                """
                body {
                    margin: 0;
                    padding: 24px;
                    background: #fff7ed;
                    color: #1f2937;
                }

                .domonic-libs-error {
                    max-width: 900px;
                    border: 1px solid #fdba74;
                    border-radius: 8px;
                    background: white;
                    padding: 20px;
                }

                .domonic-libs-error h1 {
                    margin: 0 0 8px;
                    font-size: 20px;
                }

                .domonic-libs-error pre {
                    overflow: auto;
                    border-radius: 6px;
                    background: #111827;
                    color: #f9fafb;
                    padding: 14px;
                    white-space: pre-wrap;
                }
                """
            ),
            div(
                h1("Callback error"),
                p(error["message"]),
                pre(error["traceback"]),
                _class="domonic-libs-error",
            ),
        )

    def _base_css(self):
        return """
        :root {
            color-scheme: light dark;
            font-family: -apple-system, BlinkMacSystemFont,
                         "Segoe UI", sans-serif;
        }

        body {
            margin: 0;
            padding: 2rem;
        }

        button {
            font: inherit;
            padding: 0.6rem 1rem;
        }
        """
