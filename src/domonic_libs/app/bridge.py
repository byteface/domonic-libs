from __future__ import annotations

import traceback

from .file_drop import file_drop_event
from .events import browser_event


class Bridge:
    def __init__(self, app):
        self.app = app

    def dispatch(self, handler_id: str, event_data: dict | None = None):
        handler = self.app._handlers.get(handler_id)

        if handler is None:
            raise RuntimeError(f"Unknown event handler: {handler_id}")

        try:
            event = browser_event(event_data)
            result = handler(event)
        except Exception as error:
            return self.app._handle_callback_error(error, traceback.format_exc())

        if result is False:
            return {}

        return {"html": self.app._render_route("/")}

    def tick(self, timer_id: str):
        handler = self.app._timers.get(timer_id)

        if handler is None:
            raise RuntimeError(f"Unknown timer: {timer_id}")

        try:
            result = handler()
        except Exception as error:
            return self.app._handle_callback_error(error, traceback.format_exc())

        if result is False:
            return {}

        return {"html": self.app._render_route("/")}

    def file_drop(self, files: list[dict] | None = None):
        try:
            result = self.app._dispatch_file_drop(file_drop_event(files))
        except Exception as error:
            return self.app._handle_callback_error(error, traceback.format_exc())

        if result is False:
            return {}

        return {"html": self.app._render_route("/")}
