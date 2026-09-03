# Ported from mixmark-io/turndown (MIT). Preserve the upstream licence when
# redistributing. Mirrors src/utilities.js.
"""Shared helpers: block/void tables, markdown escaping, newline trimming."""

from __future__ import annotations

import re


def extend(destination, *sources):
    """``Object.assign``-style shallow merge used to build the options dict."""
    for source in sources:
        if not source:
            continue
        for key, value in source.items():
            destination[key] = value
    return destination


def repeat(character, count):
    return character * count


def trim_leading_newlines(string):
    return re.sub(r"^\n*", "", string)


def trim_trailing_newlines(string):
    # avoid a match-at-end regexp bottleneck, see turndown#370
    index_end = len(string)
    while index_end > 0 and string[index_end - 1] == "\n":
        index_end -= 1
    return string[:index_end]


def trim_newlines(string):
    return trim_trailing_newlines(trim_leading_newlines(string))


def node_name(node):
    """Upper-case tag name.

    The DOM spec says ``Element.nodeName`` is upper-case for HTML elements in an
    HTML document; domonic returns it lower-case, so every tag comparison in
    this port goes through here. See ``docs/domonic-wrinkles.md``.
    """
    return (getattr(node, "nodeName", "") or getattr(node, "tagName", "") or "").upper()


BLOCK_ELEMENTS = [
    "ADDRESS", "ARTICLE", "ASIDE", "AUDIO", "BLOCKQUOTE", "BODY", "CANVAS",
    "CENTER", "DD", "DIR", "DIV", "DL", "DT", "FIELDSET", "FIGCAPTION", "FIGURE",
    "FOOTER", "FORM", "FRAMESET", "H1", "H2", "H3", "H4", "H5", "H6", "HEADER",
    "HGROUP", "HR", "HTML", "ISINDEX", "LI", "MAIN", "MENU", "NAV", "NOFRAMES",
    "NOSCRIPT", "OL", "OUTPUT", "P", "PRE", "SECTION", "TABLE", "TBODY", "TD",
    "TFOOT", "TH", "THEAD", "TR", "UL",
]

VOID_ELEMENTS = [
    "AREA", "BASE", "BR", "COL", "COMMAND", "EMBED", "HR", "IMG", "INPUT",
    "KEYGEN", "LINK", "META", "PARAM", "SOURCE", "TRACK", "WBR",
]

MEANINGFUL_WHEN_BLANK_ELEMENTS = [
    "A", "TABLE", "THEAD", "TBODY", "TFOOT", "TH", "TD", "IFRAME", "SCRIPT",
    "AUDIO", "VIDEO",
]


def _is(node, tag_names):
    return node_name(node) in tag_names


def _has(node, tag_names):
    if not hasattr(node, "getElementsByTagName"):
        return False
    return any(len(node.getElementsByTagName(tag_name)) for tag_name in tag_names)


def is_block(node):
    return _is(node, BLOCK_ELEMENTS)


def is_void(node):
    return _is(node, VOID_ELEMENTS)


def has_void(node):
    return _has(node, VOID_ELEMENTS)


def is_meaningful_when_blank(node):
    return _is(node, MEANINGFUL_WHEN_BLANK_ELEMENTS)


def has_meaningful_when_blank(node):
    return _has(node, MEANINGFUL_WHEN_BLANK_ELEMENTS)


def escape_markdown(string):
    """Escape Markdown syntax. Order mirrors ``markdownEscapes`` in utilities.js.

    ``re.sub`` replacements are written as functions so backslashes stay literal
    rather than being reinterpreted as replacement-template escapes.
    """
    string = string.replace("\\", "\\\\")
    string = string.replace("*", "\\*")
    string = re.sub(r"^-", lambda m: "\\-", string)
    string = re.sub(r"^\+ ", lambda m: "\\+ ", string)
    string = re.sub(r"^(=+)", lambda m: "\\" + m.group(1), string)
    string = re.sub(r"^(#{1,6}) ", lambda m: "\\" + m.group(1) + " ", string)
    string = string.replace("`", "\\`")
    string = re.sub(r"^~~~", lambda m: "\\~~~", string)
    string = string.replace("[", "\\[")
    string = string.replace("]", "\\]")
    string = re.sub(r"^>", lambda m: "\\>", string)
    string = string.replace("_", "\\_")
    string = re.sub(r"^(\d+)\. ", lambda m: m.group(1) + "\\. ", string)
    return string
