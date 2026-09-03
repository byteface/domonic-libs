from __future__ import annotations

import inspect
import json
import traceback
from typing import Any, Callable

from webview.menu import Menu, MenuAction, MenuSeparator

from .events import Event


def accepts_event(callback: Callable[..., Any]):
    signature = inspect.signature(callback)

    for parameter in signature.parameters.values():
        if parameter.kind == parameter.VAR_POSITIONAL:
            return True
        if (
            parameter.kind
            in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
            and parameter.default is parameter.empty
        ):
            return True

    return False


class MenuBuilder:
    def __init__(self, app):
        self.app = app

    def menu(self, title: str, *items: Any):
        menu = Menu(title, list(items))
        self.app._menus.append(menu)
        return menu

    def submenu(self, title: str, *items: Any):
        return Menu(title, list(items))

    def item(
        self,
        title: str,
        callback: Callable[..., Any],
        *,
        refresh: bool = True,
    ):
        return MenuAction(title, self.callback(callback, refresh=refresh))

    def separator(self):
        return MenuSeparator()

    def callback(self, callback: Callable[..., Any], *, refresh: bool):
        def handler():
            try:
                if accepts_event(callback):
                    result = callback(Event("menu"))
                else:
                    result = callback()
            except Exception as error:
                response = self.app._handle_callback_error(
                    error,
                    traceback.format_exc(),
                )
                if self.app.window is not None:
                    self.app.window.evaluate_js(
                        "document.body.innerHTML = "
                        f"{json.dumps(response['html'])}"
                    )
                return response

            if refresh and result is not False and self.app.window is not None:
                self.app.refresh()

            return result

        return handler
