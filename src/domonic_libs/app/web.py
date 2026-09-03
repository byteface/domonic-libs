"""``BrowserApp`` -- ``BaseApp`` served to an ordinary browser over HTTP.

Same render loop as ``DesktopApp``; the transport is a small stdlib
``http.server``. The client posts event payloads to ``/__domonic/dispatch`` (and
``/tick``, ``/file_drop``) and applies the ``{html}`` that comes back.

There is no server->client push, so ``evaluate_js`` / ``refresh`` called from
Python queue a *command* that rides back on the next response
(``applyCommands`` on the client). Fine for follow-up effects after an event or
a timer tick; a fire-and-forget ``evaluate_js`` with no pending interaction will
not run until the next round-trip.
"""

from __future__ import annotations

import json
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from .core import BaseApp

_TRANSPORT_JS = """
window.__domonicUI.transport = function (method, args) {
    return fetch("/__domonic/" + method, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(args || [])
    }).then(function (response) {
        return response.json();
    });
};
"""


class BrowserApp(BaseApp):
    client_ready_event = "DOMContentLoaded"

    def __init__(self, title: str, **kwargs):
        super().__init__(title, **kwargs)
        self._commands = threading.local()
        self._server: ThreadingHTTPServer | None = None

    # -- client bridge --------------------------------------------------------

    def _client_bootstrap(self) -> str:
        return _TRANSPORT_JS

    def _pending(self) -> list[dict]:
        if not hasattr(self._commands, "queue"):
            self._commands.queue = []
        return self._commands.queue

    def _drain_commands(self) -> list[dict]:
        queue = self._pending()
        drained = list(queue)
        queue.clear()
        return drained

    def evaluate_js(self, code: str, callback: Callable[..., Any] | None = None):
        # No return channel over plain HTTP -- callback is ignored.
        self._pending().append({"op": "eval", "code": code})
        return None

    def refresh(self, path: str = "/"):
        self._pending().append({"op": "html", "html": self._render_route(path)})
        return None

    # -- response assembly --------------------------------------------------

    def _respond(self, result: dict | None) -> dict:
        payload = dict(result or {})
        commands = self._drain_commands()
        if commands:
            payload.setdefault("commands", []).extend(commands)
        return payload

    # -- server -----------------------------------------------------------

    def run(self, host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True):
        app = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: D401 - silence default logging
                if app.debug:
                    super().log_message(*args)

            def _send(self, status: int, body: bytes, content_type: str):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path not in ("/", "/index.html"):
                    self._send(404, b"not found", "text/plain")
                    return
                doc = "<!doctype html>" + str(app._build_document())
                self._send(200, doc.encode("utf-8"), "text/html; charset=utf-8")

            def do_POST(self):
                if not self.path.startswith("/__domonic/"):
                    self._send(404, b"not found", "text/plain")
                    return
                method = self.path[len("/__domonic/"):]
                length = int(self.headers.get("Content-Length", 0) or 0)
                try:
                    args = json.loads(self.rfile.read(length) or b"[]")
                except ValueError:
                    args = []

                bridge_method = {
                    "dispatch": app._bridge.dispatch,
                    "tick": app._bridge.tick,
                    "file_drop": app._bridge.file_drop,
                }.get(method)

                if bridge_method is None:
                    self._send(404, b"unknown method", "text/plain")
                    return

                try:
                    result = bridge_method(*args)
                except Exception as error:  # noqa: BLE001 - surfaced to the client
                    result = app._handle_callback_error(error, traceback.format_exc())

                body = json.dumps(app._respond(result)).encode("utf-8")
                self._send(200, body, "application/json")

        self._server = ThreadingHTTPServer((host, port), Handler)
        url = f"http://{host}:{port}/"
        if open_browser:
            threading.Timer(0.4, lambda: webbrowser.open(url)).start()
        print(f"domonic-libs BrowserApp serving {url}  (Ctrl-C to stop)")
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._server.shutdown()
            self._server.server_close()
