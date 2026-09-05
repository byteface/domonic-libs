"""``myjs`` command line: run a script, render an HTML page, evaluate a snippet, or start a REPL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from ._engine import JSError, PrintConsole, Session


def _examples_dir() -> Path | None:
    try:
        from importlib.resources import files
        d = files("myjs") / "examples"
        return Path(str(d)) if d.is_dir() else None
    except Exception:
        d = Path(__file__).parent / "examples"
        return d if d.is_dir() else None


def _first_comment(path: Path) -> str:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip().strip('"').strip("'")
        s = s.removeprefix("<!--").removesuffix("-->").strip()
        s = s.removeprefix("//").removeprefix("#").strip()
        if not s or set(s) <= {"=", "-", "/", "*"}:
            continue
        if s.startswith(("<!", "<html", "import ", "from ", "const ", "let ", "var ")):
            continue
        return s if len(s) <= 74 else s[:71] + "..."
    return ""


def _examples(name: str | None, run: bool) -> int:
    d = _examples_dir()
    if d is None:
        print("myjs: examples not found in this install", file=sys.stderr)
        return 1
    files = sorted(p for p in d.iterdir() if p.suffix in (".js", ".py", ".html")
                   and p.name != "report-util.js")
    if not name:
        print("bundled examples — `myjs examples <name>` to view, `--run` to run:\n")
        w = max(len(p.stem) for p in files)
        for p in files:
            print(f"  {p.stem.ljust(w)}  {_first_comment(p)}")
        return 0
    match = next((p for p in files if p.stem == name or p.name == name), None)
    if match is None:
        print(f"myjs: no example {name!r} (try `myjs examples`)", file=sys.stderr)
        return 1
    if run:
        return main([str(match)])
    print(match.read_text(encoding="utf-8"), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="myjs",
        description="A JavaScript interpreter on domonic's DOM: run .js, render .html headlessly, "
                    "call native C via ffi, reach the Python ecosystem.",
    )
    p.add_argument("script", nargs="?",
                   help="a .js file to run, a .html file to render headlessly, "
                        "or `examples [name]` (omit for a REPL)")
    p.add_argument("args", nargs="*", help="arguments passed to a .js script as globalThis.argv")
    p.add_argument("--run", action="store_true", help="with `examples <name>`, run it instead of printing it")
    p.add_argument("-e", "--eval", dest="code", metavar="JS",
                   help="evaluate a string; with a .html file, evaluate it against the rendered page")
    p.add_argument("-o", "--output", metavar="FILE", help="write rendered HTML here instead of stdout")
    p.add_argument("--html", action="store_true", help="force headless-render mode for the given file")
    p.add_argument("--strip-scripts", action="store_true",
                   help="drop <script> elements after they run (static snapshot)")
    p.add_argument("-i", "--interactive", action="store_true", help="enter the REPL after running")
    p.add_argument("--gui", action="store_true",
                   help="after running, show the resulting DOM in a native window")
    p.add_argument("--version", action="version", version=f"myjs {__version__}")
    return p


def _looks_like_html(path: str) -> bool:
    return path.lower().endswith((".html", ".htm", ".xhtml"))


def _open_gui(title: str, html: str) -> int:
    try:
        import webview
    except ImportError:
        print("myjs --gui needs pywebview:  pip install 'domonic-libs[app]'", file=sys.stderr)
        return 1
    webview.create_window(title or "myjs", html=html, width=960, height=720)
    webview.start()
    return 0


def _report(exc: JSError) -> None:
    print(exc, file=sys.stderr)


def _run_html(args) -> int:
    from .html import Page

    try:
        page = Page.load(args.script, strip_scripts=args.strip_scripts,
                         echo=(args.code is None and not args.output and not args.gui))
    except FileNotFoundError:
        print(f"myjs: cannot open {args.script}", file=sys.stderr)
        return 1
    for err in page.errors:
        print(f"myjs: script error: {err}", file=sys.stderr)

    if args.code is not None:
        try:
            result = page.eval(args.code)
        except JSError as exc:
            _report(exc)
            return 1
        if result is not None:
            print(result if isinstance(result, str) else page.session.display(result))
        return 0

    html = page.serialize()
    if args.gui:
        return _open_gui(page.title, html)
    if args.output:
        Path(args.output).write_text(html, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(html)
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.script == "examples":
        return _examples(args.args[0] if args.args else None, args.run)

    if args.script and (args.html or (_looks_like_html(args.script) and args.script not in ("-",))):
        return _run_html(args)

    if args.code is not None and not args.script:
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
            return _open_gui(str(session.eval("document.title") or "myjs"), session.render_html())
        if args.interactive:
            from .repl import repl
            return repl(session)
        return 0

    from .repl import repl
    return repl()


if __name__ == "__main__":
    raise SystemExit(main())
