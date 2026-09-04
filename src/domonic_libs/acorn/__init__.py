# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Preserve the upstream
# licence when redistributing.
"""A port of the acorn JavaScript parser, built on ``domonic.javascript``.

Two goals: a pure-Python ECMAScript front end, and -- since acorn is ~90%
string / RegExp / number work -- a hard stress test of ``domonic.javascript``.
Divergences are logged in ``docs/javascript-wrinkles.md``.

The full pipeline is ported -- tokenizer, regex-literal validator, and the
recursive-descent parser (`node`, `scope`, `scopeflags`, `parseutil`, `lval`,
`expression`, `statement`, `parser`). Output is an ESTree-shaped tree of
``Node`` objects; call ``.to_dict()`` for plain nested dicts.

    from domonic_libs.acorn import parse
    tree = parse("const f = x => x * 2", {"ecmaVersion": 2022})
    tree.to_dict()   # {'type': 'Program', 'body': [...], ...}

``domonic_libs.acorn.jsx`` adds the acorn-jsx plugin (``parse_jsx``) and a
``jsx_to_python`` transform that rewrites the markup layer to domonic factories.
"""

from __future__ import annotations

from .identifier import (
    isIdentifierChar,
    isIdentifierStart,
    keywordRelationalOperator,
    keywords,
    reservedWords,
)
from .node import Node
from .parser import Parser, parse, parse_expression_at
from .state import Tokenizer
from .tokenize import Token
from .tokentype import TokenType
from .tokentype import tt as token_types
from .util import codePointToString, hasOwn, isArray, wordsRegexp
from .whitespace import isNewLine, lineBreak, nextLineBreak, skipWhiteSpace

version = "8.18.0"


def tokenizer(inp, options=None):
    return Tokenizer.tokenizer(inp, options)


def tokenize(inp, options=None):
    """Convenience: list every token in ``inp``."""
    return list(Tokenizer.tokenizer(inp, options).tokenize())


__all__ = [
    "Node",
    "Parser",
    "Token",
    "TokenType",
    "Tokenizer",
    "parse",
    "parse_expression_at",
    "codePointToString",
    "hasOwn",
    "isArray",
    "isIdentifierChar",
    "isIdentifierStart",
    "isNewLine",
    "keywordRelationalOperator",
    "keywords",
    "lineBreak",
    "nextLineBreak",
    "reservedWords",
    "skipWhiteSpace",
    "token_types",
    "tokenize",
    "tokenizer",
    "version",
    "wordsRegexp",
]
