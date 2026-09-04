"""``myjs`` command line: run a script, evaluate a snippet, or start a REPL."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from ._engine import JSError, PrintConsole, Session


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="myjs",
        description="A small JavaScript interpreter on domonic's DOM, with an ffi bridge to native C.",
    )
    p.add_argument("script", nargs="?", help="a .js file to execute (omit for a REPL)")
    p.add_argument("args", nargs="*", help="arguments passed to the script as globalThis.argv")
    p.add_argument("-e", "--eval", dest="code", metavar="JS", help="evaluate a string and print the result")
    p.add_argument("-i", "--interactive", action="store_true", help="enter the REPL after running")
    p.add_argument("--gui", action="store_true",
                   help="after running, show the DOM the script built in a native window")
    p.add_argument("--version", action="version", version=f"myjs {__version__}")
    return p


def _open_gui(session: Session) -> int:
    try:
        import webview
    except ImportError:
        print("myjs --gui needs pywebview:  pip install 'domonic-libs[app]'", file=sys.stderr)
        return 1
    try:
        title = session.eval("document.title") or "myjs"
    except JSError:
        title = "myjs"
    webview.create_window(str(title) or "myjs", html=session.render_html(),
                          width=960, height=720)
    webview.start()
    return 0


def _report(exc: JSError) -> None:
    print(exc, file=sys.stderr)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.code is not None:
        session = Session(console=PrintConsole())
        try:
            result = session.eval(args.code)
        except JSError as exc:
            _report(exc)
            return 1
        if result is not None:
            print(result if isinstance(result, str) else session.display(result))
        if args.interactive:
            from .repl import repl
            return repl(session)
        return 0

    if args.script:
        session = Session(console=PrintConsole())
        session.interp.global_env.declare("argv", list(args.args))
        try:
            session.run_file(args.script)
        except FileNotFoundError:
            print(f"myjs: cannot open {args.script}", file=sys.stderr)
            return 1
        except JSError as exc:
            _report(exc)
            return 1
        if args.gui:
            return _open_gui(session)
        if args.interactive:
            from .repl import repl
            return repl(session)
        return 0

    from .repl import repl
    return repl()


if __name__ == "__main__":
    raise SystemExit(main())
