"""myjs -- a small JavaScript interpreter for Python.

It runs a practical subset of ECMAScript (via the ``domonic_libs.acorn`` port and
its tree-walking evaluator) against domonic's server-side DOM, and hands scripts
an ``ffi`` global for calling native C libraries through ``ctypes``.

    import myjs

    myjs.eval("window.console.log('hi from myjs')")
    myjs.run("script.js")

    s = myjs.Session()
    s.eval("const x = 21;")
    s.eval("x * 2")            # -> 42

Command line: ``myjs`` starts a REPL, ``myjs file.js`` executes a file.
"""

def _read_version() -> str:
    from pathlib import Path
    f = Path(__file__).resolve().parents[2] / "VERSION"   # repo-root source checkout
    if f.is_file():
        return f.read_text().strip()
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("myjs")
    except PackageNotFoundError:
        return "0+unknown"


__version__ = _read_version()

from ._engine import JSError, Session

__all__ = ["Session", "JSError", "Page", "eval", "run", "import_js", "render", "repl", "__version__"]

_shared: Session | None = None


def _session() -> Session:
    global _shared
    if _shared is None:
        _shared = Session()
    return _shared


def eval(src: str, *, scope: dict | None = None):
    """Evaluate a string of JavaScript and return its completion value.

    With ``scope`` a throwaway :class:`Session` is used; otherwise a process-wide
    session persists definitions between calls.
    """
    return (Session(scope=scope) if scope else _session()).eval(src)


def run(path: str, *, scope: dict | None = None):
    """Execute a ``.js`` file. Returns its completion value."""
    return Session(scope=scope).run_file(path)


def import_js(path: str, *, scope: dict | None = None):
    """Run a ``.js`` file and return its ``export``ed names as a real,
    directly usable object -- ``mod.someFunction(1, 2)`` calls the actual JS
    function from plain Python, no bridge, no serialization (a JS function is
    already a real, callable Python object).

        # math.js: export function double(x) { return x * 2; }
        mod = myjs.import_js("math.js")
        mod.double(21)          # -> 42
    """
    s = Session(scope=scope)
    s.run_file(path)
    return s.exports


def render(source_or_path, *, strip_scripts: bool = False, **kw) -> str:
    """Render an HTML file/string headlessly (run its ``<script>``s against a
    DOM) and return the resulting HTML. See :class:`myjs.Page` for inspection."""
    from .html import render as _render

    return _render(source_or_path, strip_scripts=strip_scripts, **kw)


def __getattr__(name):   # lazy: `from myjs import Page`
    if name == "Page":
        from .html import Page
        return Page
    raise AttributeError(name)


def repl(**kwargs) -> int:
    """Start the interactive REPL. Returns a process exit code."""
    from .repl import repl as _repl

    return _repl(**kwargs)
