"""The ``myjs`` interactive REPL.

Uses ``readline`` when available for history (persisted to
``~/.config/myjs/history``), line editing, reverse search, and TAB completion of
globals and ``obj.member`` chains. Falls back to plain ``input()`` otherwise.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import __version__
from ._engine import JSError, PrintConsole, Session
from .html import Page

_HISTORY = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "myjs" / "history"

_HELP = """\
  .help            this message
  .exit / .quit    leave
  .clear           reset the session (fresh globals)
  .load <file>     run a .js file, or render a .html file, into the session
  .save <file>     write this session's input history to a file
  .editor          multi-line paste mode (finish with a blank line)
  _                the last result

  Globals: console, document, window, fetch, WebSocket, fs, sh, http, os,
           process, py, ffi, and ~190 DOM/Web-API constructors. Top-level
           await works. TAB completes names and members."""


# -- multi-line detection ------------------------------------------------

def _incomplete(src: str) -> bool:
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
    return depth > 0 or quote == "`" or src.rstrip().endswith(("=>", "&&", "||", "+", "-", "?", ":", ","))


# -- result display ----------------------------------------------------

# Node-style: colored when stdout is a real terminal (never inside `NO_COLOR`
# or a pipe), and broken into indented multi-line form once a value's compact
# one-line rendering would run past `_WRAP_AT` columns -- matching how a real
# REPL's `util.inspect` reads for anything bigger than a small flat object.
_WRAP_AT = 72
_ANSI = {
    "dim": "\033[2m", "reset": "\033[0m",
    "num": "\033[33m", "str": "\033[32m", "fn": "\033[36m",
}


def _use_color() -> bool:
    return not os.environ.get("NO_COLOR") and sys.stdout.isatty()


def _c(kind: str, text: str) -> str:
    return f"{_ANSI[kind]}{text}{_ANSI['reset']}" if _use_color() else text


def _display(value, *, _seen: frozenset = frozenset(), _indent: int = 0) -> str:
    from domonic_libs.acorn.interpret import (
        UNDEFINED, JSArray, JSObject, JSFunction, JSClass, _Promise, _stringify,
    )
    if isinstance(value, _Promise):
        # `_Promise.__repr__` (used by real coercion, e.g. `String(p)`,
        # which per spec must NOT leak the settled value) always shows just
        # `Promise { <fulfilled> }` with no value -- a real REPL's inspect
        # shows the settled value itself, the same way Node does.
        if value.state == "pending":
            return "Promise { <pending> }"
        if value.state == "rejected":
            return f"Promise {{ <rejected> {_display(value.value, _seen=_seen, _indent=_indent)} }}"
        return f"Promise {{ {_display(value.value, _seen=_seen, _indent=_indent)} }}"
    if value is UNDEFINED or value is None:
        return _c("dim", "undefined" if value is UNDEFINED else "null")
    if isinstance(value, str) and value.startswith("@@"):
        # a Symbol -- represented internally as an opaque `@@`-prefixed
        # string (see `_symbol_ctor`), not a real unique primitive; shown
        # as its literal string value before this, `Symbol('x')` printed
        # as the quoted string `'@@sym:x:1'` -- meaningless to a reader and
        # nothing like the real `Symbol(x)` a REPL should show.
        body = value[2:]
        if body.startswith("sym:"):
            desc, _, _n = body[4:].rpartition(":")
            return _c("fn", f"Symbol({desc})")
        if body.startswith("for:"):
            return _c("fn", f"Symbol.for({body[4:]!r})")
        return _c("fn", f"Symbol.{body}")   # a well-known symbol: iterator, ...
    if isinstance(value, str):
        return _c("str", repr(value))
    if isinstance(value, bool):
        return _c("num", "true" if value else "false")
    if isinstance(value, (int, float)):
        return _c("num", _stringify(value))
    if isinstance(value, (JSFunction, JSClass)):
        name = getattr(value, "name", "") or "anonymous"
        kind = "Class" if isinstance(value, JSClass) else "Function"
        return _c("fn", f"[{kind}: {name}]")

    if isinstance(value, (JSArray, list, dict)):
        if id(value) in _seen:
            return _c("dim", "[Circular]")
        seen = _seen | {id(value)}
        is_dict = isinstance(value, dict)
        items = list(value.items())[:100] if is_dict else list(value[:100])
        more = len(value) - len(items)
        if is_dict:
            rendered = [f"{k}: {_display(v, _seen=seen, _indent=_indent + 1)}" for k, v in items]
        else:
            rendered = [_display(x, _seen=seen, _indent=_indent + 1) for x in items]
        open_, close = ("{", "}") if is_dict else ("[", "]")
        if not rendered:
            return open_ + close
        compact = f"{open_} " + ", ".join(rendered) + f" {close}"
        if len(compact) <= _WRAP_AT and "\n" not in compact:
            return compact
        pad, closing_pad = "  " * (_indent + 1), "  " * _indent
        body = ",\n".join(pad + r for r in rendered)
        tail = f",\n{pad}... {more} more" if more > 0 else ""
        return f"{open_}\n{body}{tail}\n{closing_pad}{close}"

    tn = type(value).__name__
    if type(value).__module__ == "domonic.javascript" and tn in ("RegExp", "Date", "Map", "Set"):
        # `RegExp`/`Date`/`Map`/`Set` are real `domonic.javascript` classes
        # with no special-casing above -- they used to fall all the way
        # through to the generic `_stringify` fallback, which has no
        # notion of any of these (a regex literal lost its `/.../flags`
        # notation entirely; `Map`/`Set` printed as a bare Python
        # `str(self.args)`, indistinguishable from a plain array or tuple
        # list). Shown the way a real REPL shows them instead.
        if tn == "RegExp":
            return _c("str", f"/{value.source}/{value.flags}")
        if tn == "Date":
            try:
                return _c("num", value.toISOString())
            except Exception:
                pass
        if tn == "Map":
            try:
                entries = list(value.entries())
            except Exception:
                entries = []
            body = ", ".join(
                f"{_display(k, _seen=_seen, _indent=_indent + 1)} => "
                f"{_display(v, _seen=_seen, _indent=_indent + 1)}" for k, v in entries)
            return f"Map({len(entries)}) {{{' ' + body + ' ' if body else ''}}}"
        if tn == "Set":
            try:
                items = list(value)
            except Exception:
                items = []
            body = ", ".join(_display(x, _seen=_seen, _indent=_indent + 1) for x in items)
            return f"Set({len(items)}) {{{' ' + body + ' ' if body else ''}}}"
    if hasattr(value, "outerHTML") or tn in ("html", "body", "div"):  # a DOM node
        s = str(value)
        return s if len(s) <= 400 else s[:397] + "..."
    return _stringify(value)


# -- completion --------------------------------------------------------

def _completer(session: Session):
    import re
    ident_chain = re.compile(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\.?$")

    def names_of(obj):
        from domonic_libs.acorn.interpret import JSInstance
        try:
            if isinstance(obj, dict):
                out = list(obj.keys())
                if isinstance(obj, JSInstance):
                    out += list(getattr(obj._cls, "methods", {}))
                return out
            return [a for a in dir(obj) if not a.startswith("_")]
        except Exception:
            return []

    def complete(text, state):
        line = _readline_buffer()
        m = ident_chain.search(line[: _readline_point()])
        try:
            if m and "." in m.group(1):
                base, _, partial = m.group(1).rpartition(".")
                obj = session.eval(base)
                cands = [f"{base}.{n}" for n in names_of(obj) if n.startswith(partial)]
            else:
                partial = m.group(1) if m else ""
                seen = set()
                cands = []
                env = session.interp.global_env
                while env is not None:
                    for k in env.vars:
                        if k.startswith(partial) and k not in seen:
                            seen.add(k)
                            cands.append(k)
                    env = env.parent
                for k in getattr(session.window, "_own", {}):
                    if k.startswith(partial) and k not in seen:
                        seen.add(k)
                        cands.append(k)
                if line.lstrip().startswith(".") and not line.lstrip()[1:].strip():
                    cands = [c for c in (".help", ".exit", ".clear", ".load", ".save", ".editor")]
            cands.sort()
            return cands[state] if state < len(cands) else None
        except Exception:
            return None

    return complete


def _readline_buffer():
    try:
        import readline
        return readline.get_line_buffer()
    except Exception:
        return ""


def _readline_point():
    try:
        import readline
        return readline.get_endidx()
    except Exception:
        return len(_readline_buffer())


def _setup_readline(session: Session):
    try:
        import readline
    except Exception:
        return
    _HISTORY.parent.mkdir(parents=True, exist_ok=True)
    try:
        readline.read_history_file(_HISTORY)
    except (FileNotFoundError, OSError):
        pass
    readline.set_history_length(2000)
    readline.set_completer(_completer(session))
    readline.set_completer_delims(" \t\n`~!@#%^&*()-=+[{]}\\|;:'\",<>/?")
    readline.parse_and_bind("tab: complete")
    import atexit
    atexit.register(lambda: _save_history())


def _save_history():
    try:
        import readline
        readline.write_history_file(_HISTORY)
    except Exception:
        pass


# -- the loop --------------------------------------------------------

def repl(session: Session | None = None) -> int:
    session = session or Session(console=PrintConsole())
    _setup_readline(session)
    tty = sys.stdin.isatty()
    if tty:
        print(f"myjs {__version__}  —  JavaScript on a real DOM.  .help  ·  Ctrl-D to exit")

    buffer = ""
    while True:
        prompt = "... " if buffer else "js> "
        try:
            line = input(prompt if tty else "")
        except EOFError:
            if tty:
                print()
            return 0
        except KeyboardInterrupt:
            print("^C")
            buffer = ""
            continue

        stripped = line.strip()
        if not buffer and stripped.startswith("."):
            done, session, buffer = _command(stripped, session)
            if done:
                return 0
            continue

        buffer = f"{buffer}\n{line}" if buffer else line
        if _incomplete(buffer):
            continue
        src, buffer = buffer, ""
        if not src.strip():
            continue
        _run(session, src)
    return 0


def _run(session: Session, src: str):
    from domonic_libs.acorn.interpret import JSThrow, UNDEFINED
    from ._engine import _reraise
    try:
        result = session.interp.run(src)   # keeps UNDEFINED vs null distinct
    except (JSThrow, SyntaxError) as exc:
        try:
            _reraise(exc)
        except JSError as je:
            print(je, file=sys.stderr)
        return
    except RecursionError:
        print("RangeError: Maximum call stack size exceeded", file=sys.stderr)
        return
    if result is not UNDEFINED and result is not None:
        session.interp.global_env.declare("_", result)
    print(_display(result))


def _command(cmd: str, session: Session):
    """Returns (should_exit, session, buffer)."""
    parts = cmd.split(None, 1)
    name, arg = parts[0], (parts[1].strip() if len(parts) > 1 else "")
    if name in (".exit", ".quit"):
        return True, session, ""
    if name == ".help":
        print(_HELP)
    elif name == ".clear":
        session = Session(console=PrintConsole())
        _setup_readline(session)
        print("(session cleared)")
    elif name == ".load":
        if not arg:
            print("usage: .load <file>", file=sys.stderr)
        elif arg.lower().endswith((".html", ".htm")):
            page = Page.load(arg)
            session.interp.global_env.declare("page", page)
            for ln in page.console_lines:
                print(ln)
            print(f"(rendered {arg} -> `page`; {len(page.errors)} script error(s))")
        else:
            from domonic_libs.acorn.interpret import JSThrow
            try:
                session.interp.run(Path(arg).read_text())
                print(f"(loaded {arg})")
            except OSError as e:
                print(f".load: {e}", file=sys.stderr)
            except (JSThrow, SyntaxError) as exc:
                from ._engine import _reraise
                try:
                    _reraise(exc)
                except JSError as je:
                    print(je, file=sys.stderr)
    elif name == ".save":
        try:
            import readline
            path = arg or "myjs-session.js"
            with open(path, "w") as fh:
                for i in range(1, readline.get_current_history_length() + 1):
                    fh.write(readline.get_history_item(i) + "\n")
            print(f"(history -> {path})")
        except Exception as e:  # noqa: BLE001
            print(f".save: {e}", file=sys.stderr)
    elif name == ".editor":
        print("// editor mode — end with a blank line")
        lines = []
        while True:
            try:
                ln = input("")
            except (EOFError, KeyboardInterrupt):
                break
            if ln == "":
                break
            lines.append(ln)
        if lines:
            _run(session, "\n".join(lines))
    else:
        print(f"unknown command {name} (.help for the list)", file=sys.stderr)
    return False, session, ""
