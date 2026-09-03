# Ported from mixmark-io/turndown (MIT). Mirrors src/node.js.
"""Decorate a DOM node with the flags the rules and converter rely on.

Like turndown.js this mutates the node in place (adding ``isBlock``, ``isCode``,
``isBlank``, ``flankingWhitespace``) and returns it, rather than wrapping it --
the rules still need the object to behave as a DOM node.
"""

from __future__ import annotations

import re

from .utilities import (
    has_meaningful_when_blank,
    has_void,
    is_block,
    is_meaningful_when_blank,
    is_void,
    node_name,
)

_BLANK = re.compile(r"\s*\Z", re.IGNORECASE)
_EDGE_WHITESPACE = re.compile(
    r"^(([ \t\r\n]*)(\s*))(?:(?=\S)[\s\S]*\S)?((\s*?)([ \t\r\n]*))\Z"
)


def decorate_node(node, options):
    node.isBlock = is_block(node)
    node.isCode = node_name(node) == "CODE" or bool(
        getattr(node.parentNode, "isCode", False)
    )
    node.isBlank = _is_blank(node)
    node.flankingWhitespace = _flanking_whitespace(node, options)
    return node


def _is_blank(node):
    return (
        not is_void(node)
        and not is_meaningful_when_blank(node)
        and bool(_BLANK.match(node.textContent or ""))
        and not has_void(node)
        and not has_meaningful_when_blank(node)
    )


def _flanking_whitespace(node, options):
    if node.isBlock or (options.get("preformattedCode") and node.isCode):
        return {"leading": "", "trailing": ""}

    edges = _edge_whitespace(node.textContent or "")
    leading = edges["leading"]
    trailing = edges["trailing"]

    # abandon leading ASCII whitespace if left-flanked by ASCII whitespace
    if edges["leadingAscii"] and _is_flanked_by_whitespace("left", node, options):
        leading = edges["leadingNonAscii"]

    # abandon trailing ASCII whitespace if right-flanked by ASCII whitespace
    if edges["trailingAscii"] and _is_flanked_by_whitespace("right", node, options):
        trailing = edges["trailingNonAscii"]

    return {"leading": leading, "trailing": trailing}


def _edge_whitespace(string):
    m = _EDGE_WHITESPACE.match(string)
    return {
        "leading": m.group(1),  # whole string for whitespace-only strings
        "leadingAscii": m.group(2),
        "leadingNonAscii": m.group(3),
        "trailing": m.group(4),  # empty for whitespace-only strings
        "trailingNonAscii": m.group(5),
        "trailingAscii": m.group(6),
    }


def _is_flanked_by_whitespace(side, node, options):
    if side == "left":
        sibling = node.previousSibling
        regexp = re.compile(r" $")
    else:
        sibling = node.nextSibling
        regexp = re.compile(r"^ ")

    is_flanked = None
    if sibling:
        if sibling.nodeType == 3:
            is_flanked = bool(regexp.search(sibling.nodeValue or ""))
        elif options.get("preformattedCode") and node_name(sibling) == "CODE":
            is_flanked = False
        elif sibling.nodeType == 1 and not is_block(sibling):
            is_flanked = bool(regexp.search(sibling.textContent or ""))
    return is_flanked
