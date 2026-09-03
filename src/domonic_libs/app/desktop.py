"""``DesktopApp`` -- ``BaseApp`` hosted in a pywebview window.

The transport is pywebview's ``js_api`` object (``Bridge``); ``evaluate_js`` and
the ``document.body.innerHTML`` swaps go straight down ``window.evaluate_js``.
Native menus, file dialogs and native-path drag/drop live here because they have
no browser equivalent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import webview

from .core import BaseApp, EventHandler
from .file_drop import enable_native_file_drop
from .menus import MenuBuilder


class DesktopApp(BaseApp):
    client_ready_event = "pywebviewready"

    def __init__(
        self,
        title: str,
        *,
        width: int = 800,
        height: int = 600,
        debug: bool = False,
        data_dir: str | Path | None = None,
        transparent: bool = False,
        background_color: str = "#FFFFFF",
        frameless: bool = False,
        vibrancy: bool = False,
        text_select: bool = False,
    ):
        super().__init__(title, data_dir=data_dir, debug=debug)

        if not re.fullmatch(r"#[0-9a-fA-F]{6}", background_color):
            raise ValueError(
                "background_color must be a 6-digit hex color such as "
                '"#000000"; use transparent=True for window transparency'
            )

        self.width = width
        self.height = height
        self.transparent = transparent
        self.background_color = background_color
        self.frameless = frameless
        self.vibrancy = vibrancy
        self.text_select = text_select

        self.window = None
        self._menu_builder = MenuBuilder(self)
        self._native_file_drop_enabled = False

    # -- lifecycle -------------------------------------------------------------

    def run(self):
        document = self._build_document()

        self.window = webview.create_window(
            self.title,
            html="<!doctype html>" + str(document),
            js_api=self._bridge,
            width=self.width,
            height=self.height,
            background_color=self.background_color,
            transparent=self.transparent,
            frameless=self.frameless,
            vibrancy=self.vibrancy,
            text_select=self.text_select,
            menu=self._menus,
        )

        webview.start(debug=self.debug)

    # -- client bridge --------------------------------------------------------

    def evaluate_js(self, code: str, callback: Callable[..., Any] | None = None):
        if self.window is None:
            raise RuntimeError("The application window is not running")
        return self.window.evaluate_js(code, callback=callback)

    def refresh(self, path: str = "/"):
        if self.window is None:
            raise RuntimeError("The application window is not running")
        markup = self._render_route(path)
        return self.window.evaluate_js(
            f"document.body.innerHTML = {json.dumps(markup)}"
        )

    # -- editor commands ----------------------------------------------------

    def _editor_command(self, command: str):
        self.evaluate_js(f"document.execCommand({json.dumps(command)})")
        return False

    def cut(self):
        return self._editor_command("cut")

    def copy(self):
        return self._editor_command("copy")

    def paste(self):
        return self._editor_command("paste")

    def select_all(self):
        return self._editor_command("selectAll")

    # -- native file drop ----------------------------------------------------

    def on_file_drop(self, callback: EventHandler):
        super().on_file_drop(callback)
        if not self._native_file_drop_enabled:
            enable_native_file_drop()
            self._native_file_drop_enabled = True
        return callback

    # -- native menus -------------------------------------------------------

    def menu(self, title: str, *items: Any):
        return self._menu_builder.menu(title, *items)

    def submenu(self, title: str, *items: Any):
        return self._menu_builder.submenu(title, *items)

    def menu_item(self, title: str, callback: Callable[..., Any], *, refresh: bool = True):
        return self._menu_builder.item(title, callback, refresh=refresh)

    def menu_separator(self):
        return self._menu_builder.separator()

    # -- native file dialogs ----------------------------------------------

    def open_file(
        self,
        *,
        allow_multiple: bool = False,
        file_types: tuple[str, ...] = (),
    ):
        if self.window is None:
            raise RuntimeError("The application window is not running")
        return self.window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=allow_multiple,
            file_types=file_types,
        )

    def open_folder(self):
        if self.window is None:
            raise RuntimeError("The application window is not running")
        return self.window.create_file_dialog(webview.FileDialog.FOLDER)

    def save_file(self, *, filename: str = "", file_types: tuple[str, ...] = ()):
        if self.window is None:
            raise RuntimeError("The application window is not running")
        return self.window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=filename,
            file_types=file_types,
        )
