"""The ``myjs`` interactive REPL."""

from __future__ import annotations

import sys

from . import __version__
from ._engine import JSError, PrintConsole, Session


def _incomplete(src: str) -> bool:
    """True if ``src`` has unclosed brackets / strings / block comments -- a
    cheap heuristic so the REPL keeps reading multi-line input."""
    depth = 0
    i, n = 0, len(src)
    quote = None
    while i < n:
        c = src[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == "/" and i + 1 < n and src[i + 1] == "/":
            nl = src.find("\n", i)
            if nl == -1:
                return False
            i = nl
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            if end == -1:
                return True
            i = end + 1
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        i += 1
    return depth > 0 or quote in ('`',)


def repl(session: Session | None = None) -> int:
    session = session or Session(console=PrintConsole())
    print(f"myjs {__version__} - JavaScript on domonic. Ctrl-D or .exit to quit, .help for help.")
    buffer = ""
    while True:
        prompt = "... " if buffer else "js> "
        try:
            line = input(prompt)
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("^C")
            buffer = ""
            continue

        if not buffer and line.strip() in (".exit", ".quit"):
            return 0
        if not buffer and line.strip() == ".help":
            print("  .exit    quit\n  .clear   reset the session\n  .help    this message\n"
                  "  _        the last result\n  ffi, os  native bindings; window/document the DOM")
            continue
        if not buffer and line.strip() == ".clear":
            session = Session(console=PrintConsole())
            print("(session cleared)")
            continue

        buffer = f"{buffer}\n{line}" if buffer else line
        if _incomplete(buffer):
            continue

        src, buffer = buffer, ""
        if not src.strip():
            continue
        try:
            result = session.eval(src)
        except JSError as exc:
            print(exc, file=sys.stderr)
            continue
        except RecursionError:
            print("RangeError: Maximum call stack size exceeded", file=sys.stderr)
            continue
        if result is not None:
            session.interp.global_env.declare("_", result)
            print(session.display(result))
    return 0
