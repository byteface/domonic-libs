"""The myjs session: a persistent JS interpreter over domonic's DOM + ``ffi``."""

from __future__ import annotations

import atexit
import re
import shutil
import sys
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

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _rows(line: str) -> int:
    """How many terminal rows ``line`` actually occupies once printed --
    ANSI colour codes don't count toward the visible width, an embedded
    ``\\n`` starts a new row of its own, and a row wider than the terminal
    wraps onto more than one."""
    cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    total = 0
    for part in line.split("\n"):
        width = len(_ANSI_RE.sub("", part))
        total += max(1, -(-width // cols)) if cols > 0 else 1   # ceil division
    return total


class PrintConsole(_Console):
    """Captures like the base console, and echoes each line as it is emitted
    (``console.error`` / ``warn`` / ``assert`` go to stderr)."""

    def __init__(self):
        super().__init__()
        self._frame_rows = 0   # terminal rows drawn since the last clear()
        self._cursor_hidden = False

    def _emit(self, text, stream="out"):
        r = super()._emit(text, stream)
        line = self.lines[-1]
        if stream != "err":   # a live dashboard's frame is its stdout only
            self._frame_rows += _rows(line)
        print(line, file=sys.stderr if stream == "err" else sys.stdout)
        return r

    def clear(self, *_):
        # the base class only empties the captured-lines buffer -- harmless
        # for a Session under test, but on a live terminal this used to
        # `print("\x1b[2J\x1b[H")` -- erase the *entire visible terminal*
        # and jump the cursor to its absolute top-left -- on every single
        # tick of a `setInterval(render, ...)` dashboard (sysmon.js,
        # cockpit.js, ...). That blanks the whole screen for a moment before
        # the new frame streams back in, which is the visible "flash", and
        # it repaints from the terminal's origin rather than the dashboard's
        # own position, disturbing whatever a shell/REPL printed above it.
        # Moving the cursor back up to exactly where the *previous* frame
        # started, then erasing only from there to the end of the screen,
        # redraws in place with nothing above ever touched -- the same
        # technique real terminal dashboards (htop, ...) use.
        r = super().clear(*_)
        if sys.stdout.isatty():
            if not self._cursor_hidden:
                print("\x1b[?25l", end="")   # hide the cursor while redrawing
                self._cursor_hidden = True
                atexit.register(self._show_cursor)
            if self._frame_rows:
                print(f"\x1b[{self._frame_rows}F\x1b[J", end="")
            self._frame_rows = 0
        return r

    def _show_cursor(self):
        if self._cursor_hidden and sys.stdout.isatty():
            print("\x1b[?25h", end="", flush=True)
            self._cursor_hidden = False


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
    line = getattr(exc, "js_line", None)
    trace = getattr(exc, "js_trace", None)
    if isinstance(val, dict):                       # legacy dict-shaped error
        raise JSError(val.get("message", ""), name=val.get("name", "Error"),
                      line=line, trace=trace) from None
    if val is not None and hasattr(val, "name"):    # a domonic error instance
        raise JSError(str(getattr(val, "message", "") or val),
                      name=str(getattr(val, "name", "Error")),
                      line=line, trace=trace) from None
    raise JSError(str(exc), name=type(exc).__name__, line=line, trace=trace) from None


class Session:
    """One JS global scope. Feed it source with :meth:`eval`; state persists."""

    def __init__(self, scope=None, console=None, document=None, commonjs=False):
        from . import __version__

        extra = {**_ffi_scope(), **_host_scope(__version__)}
        if scope:
            extra.update(scope)
        self.interp, self.console, self.document, self.window = make_interpreter(
            extra_globals=extra, console=console, document=document, commonjs=commonjs
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
    def exports(self):
        """The ``export``ed names of the last file run via :meth:`run_file`
        (``export function foo(){}`` etc.), as a real object -- ``mod.foo``
        *and* ``mod["foo"]`` both work, and each export is a real, directly
        callable Python object (no bridge, no serialization): ``mod.foo(1)``
        calls the actual JS function from plain Python code."""
        return self.interp._cur_module["exports"]

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
