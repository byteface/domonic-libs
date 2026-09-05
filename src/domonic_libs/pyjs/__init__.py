"""``pyjs`` -- a small Python -> JavaScript transpiler.

The mirror image of ``myjs`` (JavaScript in Python): here Python source is
walked as a CPython AST, translated to ESTree, and emitted as JavaScript by
``domonic_libs.acorn.generate``. A JS runtime shim (``runtime.js``) supplies
the Python semantics JS doesn't share.

    from domonic_libs.pyjs import transpile

    transpile("def add(a, b): return a + b", minify=True)

Supported: functions, classes (single inheritance, ``@property`` /
``@staticmethod``), ``if`` / ``while`` / ``for ... in``, comprehensions,
f-strings, tuple unpacking, ``try`` / ``except`` / ``finally``, ``raise``,
``lambda``, ``async`` / ``await``, generators, and the common builtins
(``print`` / ``range`` / ``len`` / ``str`` / ``enumerate`` / ``zip`` /
``sorted`` / ``sum`` / ``min`` / ``max`` / ``isinstance`` ...). Not (yet):
``import``, ``with``, ``**kwargs``, decorators beyond the three above,
``%``-formatting, multiple inheritance.

On the CLI: ``dlx pyjs script.py -o script.js``.
"""

from __future__ import annotations

from pathlib import Path

from domonic_libs.acorn import generate

from .translate import PyJSError, translate

__all__ = ["transpile", "transpile_file", "PyJSError", "RUNTIME"]

RUNTIME = (Path(__file__).parent / "runtime.js").read_text(encoding="utf-8")


def transpile(source: str, *, minify: bool = False, runtime: bool = True,
              indent: str = "  ") -> str:
    """Transpile Python ``source`` to a JavaScript string. ``runtime=True``
    prepends the ``__py`` runtime shim (needed unless the module happens to
    use none of it); ``minify=True`` strips whitespace from both."""
    js = generate(translate(source), minify=minify, indent=indent)
    if runtime:
        rt = generate(_parse_runtime(), minify=True) if minify else RUNTIME.rstrip()
        js = rt + ("" if minify else "\n\n") + js
    return js


def transpile_file(path: str, **kwargs) -> str:
    return transpile(Path(path).read_text(encoding="utf-8"), **kwargs)


_RUNTIME_AST = None


def _parse_runtime():
    global _RUNTIME_AST
    if _RUNTIME_AST is None:
        from domonic_libs.acorn import parse
        _RUNTIME_AST = parse(RUNTIME, {"ecmaVersion": 2022})
    return _RUNTIME_AST
