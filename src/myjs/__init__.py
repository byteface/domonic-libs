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

__all__ = ["Session", "JSError", "eval", "run", "repl", "__version__"]

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


def repl(**kwargs) -> int:
    """Start the interactive REPL. Returns a process exit code."""
    from .repl import repl as _repl

    return _repl(**kwargs)
