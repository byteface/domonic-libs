"""The myjs session: a persistent JS interpreter over domonic's DOM + ``ffi``."""

from __future__ import annotations

from pathlib import Path

from domonic_libs.acorn.interpret import (
    UNDEFINED,
    JSThrow,
    _Console,
    _stringify,
    make_interpreter,
)

from .ffi import scope as _ffi_scope
from .host import async_fetch as _async_fetch
from .host import scope as _host_scope
from .host import websocket_ctor as _websocket_ctor


class PrintConsole(_Console):
    """Captures like the base console, and echoes each line to stdout."""

    def log(self, *a):
        super().log(*a)
        print(self.lines[-1])

    warn = error = info = debug = trace = log


class JSError(Exception):
    """A JavaScript exception (or syntax error) that escaped the script."""

    def __init__(self, message, *, name="Error", line=None, trace=None):
        super().__init__(message)
        self.js_name = name
        self.js_line = line
        self.js_trace = trace

    def __str__(self):
        base = super().__str__()
        where = f"  (line {self.js_line})" if self.js_line else ""
        stack = f"\n  at {self.js_trace}" if self.js_trace else ""
        return f"{self.js_name}: {base}{where}{stack}"


def _reraise(exc):
    val = getattr(exc, "value", None)
    if isinstance(val, dict):
        raise JSError(
            val.get("message", ""),
            name=val.get("name", "Error"),
            line=getattr(exc, "js_line", None),
            trace=getattr(exc, "js_trace", None),
        ) from None
    raise JSError(
        str(exc),
        name=type(exc).__name__,
        line=getattr(exc, "js_line", None),
        trace=getattr(exc, "js_trace", None),
    ) from None


class Session:
    """One JS global scope. Feed it source with :meth:`eval`; state persists."""

    def __init__(self, scope=None, console=None):
        from . import __version__

        extra = {**_ffi_scope(), **_host_scope(__version__)}
        if scope:
            extra.update(scope)
        self.interp, self.console, self.document, self.window = make_interpreter(
            extra_globals=extra, console=console
        )
        for name, value in (
            ("fetch", _async_fetch(self.interp.loop)),
            ("WebSocket", _websocket_ctor(self.interp.loop)),
        ):
            self.interp.global_env.declare(name, value)
            self.window._own[name] = value

    def eval(self, src, ecma_version=2022):
        """Run ``src`` and return its completion value (``None`` for undefined)."""
        try:
            result = self.interp.run(src, ecma_version=ecma_version)
        except (JSThrow, SyntaxError) as exc:
            _reraise(exc)
        return None if result is UNDEFINED else result

    def run_file(self, path, ecma_version=2022):
        p = Path(path).resolve()
        self.interp.module_base = str(p.parent)
        self.interp._cur_module["dir"] = str(p.parent)
        return self.eval(p.read_text(), ecma_version=ecma_version)

    @property
    def console_lines(self):
        return list(getattr(self.console, "lines", []))

    def render_html(self):
        """Serialise the DOM the script built into a standalone HTML document."""
        try:
            title = self.document.title
        except Exception:
            title = None
        try:
            root = str(self.document.documentElement)
        except Exception:
            root = f"<html><head></head><body>{self.document.body}</body></html>"
        if title and isinstance(title, str) and "<title>" not in root:
            root = root.replace("<head>", f"<head><title>{title}</title>", 1)
        return "<!doctype html>\n" + root

    @staticmethod
    def display(value):
        """Human-readable form of a completion value, for a REPL."""
        if value is None or value is UNDEFINED:
            return "undefined"
        if isinstance(value, str):
            return repr(value)
        try:
            return _stringify(value)
        except Exception:
            return repr(value)
