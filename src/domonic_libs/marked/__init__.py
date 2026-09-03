# Ported from markedjs/marked (MIT). Preserve the upstream licence when
# redistributing. Corresponds to src/marked.ts + src/Instance.ts.
"""Python port of marked -- a Markdown-to-HTML compiler.

    from domonic_libs.marked import marked
    marked("# Hello *world*")      # '<h1>Hello <em>world</em></h1>\\n'

Options mirror marked's (``gfm``, ``breaks``, ``pedantic``, ``silent`` and a
custom ``renderer``), passed positionally as a dict or as keyword arguments.
Hooks, async, and third-party extensions are not ported.
"""

from __future__ import annotations

from .defaults import _defaults, change_defaults, get_defaults
from .lexer import Lexer
from .parser import Parser
from .renderer import Renderer
from .text_renderer import TextRenderer
from .tokenizer import Tokenizer

__all__ = [
    "marked",
    "parse",
    "parse_inline",
    "Marked",
    "Lexer",
    "Parser",
    "Renderer",
    "TextRenderer",
    "Tokenizer",
    "lexer",
    "parser",
    "get_defaults",
]


def _resolve_options(options, kwargs):
    merged = get_defaults()
    if options:
        merged.update(options)
    if kwargs:
        merged.update(kwargs)
    return merged


def marked(src, options=None, **kwargs):
    """Compile a Markdown string to HTML."""
    resolved = _resolve_options(options, kwargs)
    try:
        tokens = Lexer.lex(src, resolved)
        return Parser(resolved).parse(tokens)
    except Exception as error:  # pragma: no cover - parity with marked's silent mode
        if resolved.get("silent"):
            return (
                "<p>An error occurred:</p><pre>"
                + str(error).replace("&", "&amp;").replace("<", "&lt;")
                + "</pre>"
            )
        raise


parse = marked


def parse_inline(src, options=None, **kwargs):
    """Compile inline Markdown to HTML with no enclosing block tag."""
    resolved = _resolve_options(options, kwargs)
    tokens = Lexer.lex_inline(src, resolved)
    return Parser(resolved).parse_inline(tokens)


def lexer(src, options=None, **kwargs):
    return Lexer.lex(src, _resolve_options(options, kwargs))


def parser(tokens, options=None, **kwargs):
    return Parser(_resolve_options(options, kwargs)).parse(tokens)


class Marked:
    """A configurable instance, matching marked's ``Marked`` class (subset)."""

    def __init__(self):
        self.defaults = get_defaults()

    def set_options(self, options):
        self.defaults.update(options)
        change_defaults(self.defaults)
        return self

    setOptions = set_options

    def parse(self, src, options=None, **kwargs):
        merged = dict(self.defaults)
        if options:
            merged.update(options)
        merged.update(kwargs)
        return marked(src, merged)

    def parse_inline(self, src, options=None, **kwargs):
        merged = dict(self.defaults)
        if options:
            merged.update(options)
        merged.update(kwargs)
        return parse_inline(src, merged)
