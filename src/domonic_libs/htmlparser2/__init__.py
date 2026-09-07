# Ported from fb55/htmlparser2 (MIT). Preserve the upstream license when redistributing.
"""A faithful-shape Python port of htmlparser2, backed by domonic DOM nodes.

This port keeps htmlparser2's public API and callback contract:
``Parser``, ``Tokenizer``, ``DomHandler``, ``parseDocument``,
``createDocumentStream`` and ``parseFeed``. The parser stack, void element
rules, implied-close rules and foreign-context casing tables mirror upstream
``src/Parser.ts``. The tokenizer mirrors upstream ``src/Tokenizer.ts``'s
state-method layout, including raw-text / RCDATA / plaintext paths.
"""

from __future__ import annotations

from .parser import Handler, Parser, ParserOptions
from .tokenizer import QuoteType, Tokenizer
from .domhandler import DomHandler, DomHandlerOptions, DefaultHandler, ElementType
from .domutils import (
    DomUtils,
    append,
    appendChild,
    filter,
    find,
    getElementById,
    getElementsByClassName,
    getElementsByTagName,
    getInnerHTML,
    getOuterHTML,
    innerText,
    prepend,
    prependChild,
    removeElement,
    replaceElement,
    textContent,
)
from .feed import getFeed, parseFeed
from .domonic_adapter import install as install_domonic_parser, uninstall as uninstall_domonic_parser


Options = ParserOptions


def parseDocument(data: str, options: dict | None = None):
    handler = DomHandler(None, options)
    Parser(handler, options).end(data)
    return handler.root


def parseDOM(data: str, options: dict | None = None):
    return parseDocument(data, options).args


def createDocumentStream(callback, options: dict | None = None, elementCallback=None):
    holder = {}

    def done(error=None, dom=None):
        callback(error, holder["handler"].root)

    handler = DomHandler(done, options, elementCallback)
    holder["handler"] = handler
    return Parser(handler, options)


def createDomStream(callback, options: dict | None = None, elementCallback=None):
    return createDocumentStream(callback, options, elementCallback)


parseDOMStream = createDomStream


__all__ = [
    "DefaultHandler",
    "DomHandler",
    "DomHandlerOptions",
    "DomUtils",
    "ElementType",
    "Handler",
    "Options",
    "Parser",
    "ParserOptions",
    "QuoteType",
    "Tokenizer",
    "append",
    "appendChild",
    "createDomStream",
    "createDocumentStream",
    "filter",
    "find",
    "getElementById",
    "getElementsByClassName",
    "getElementsByTagName",
    "getFeed",
    "getInnerHTML",
    "getOuterHTML",
    "innerText",
    "install_domonic_parser",
    "parseDOM",
    "parseDOMStream",
    "parseDocument",
    "parseFeed",
    "prepend",
    "prependChild",
    "removeElement",
    "replaceElement",
    "textContent",
    "uninstall_domonic_parser",
]
