# Ported from mixmark-io/turndown (MIT), which adapts collapse-whitespace by
# Luc Thevenard (MIT). Mirrors src/collapse-whitespace.js.
"""Collapse runs of insignificant whitespace in a DOM subtree, in place."""

from __future__ import annotations

import re

from .utilities import node_name

_WS_RUN = re.compile(r"[ \r\n\t]+")
_TRAILING_SPACE = re.compile(r" $")


def collapse_whitespace(options):
    element = options["element"]
    is_block = options["isBlock"]
    is_void = options["isVoid"]
    is_pre = options.get("isPre") or (lambda node: node_name(node) == "PRE")

    if not element.firstChild or is_pre(element):
        return

    prev_text = None
    keep_leading_ws = False

    prev = None
    node = _next(prev, element, is_pre)

    while node is not element:
        if node.nodeType in (3, 4):  # TEXT_NODE or CDATA_SECTION_NODE
            text = _WS_RUN.sub(" ", node.data)

            if (
                (not prev_text or prev_text.data.endswith(" "))
                and not keep_leading_ws
                and text[:1] == " "
            ):
                text = text[1:]

            # `text` might be empty at this point.
            if not text:
                node = _remove(node)
                continue

            node.data = text
            prev_text = node
        elif node.nodeType == 1:  # ELEMENT_NODE
            if is_block(node) or node_name(node) == "BR":
                if prev_text:
                    prev_text.data = _TRAILING_SPACE.sub("", prev_text.data)
                prev_text = None
                keep_leading_ws = False
            elif is_void(node) or is_pre(node):
                # Avoid trimming space around non-block, non-BR void elements
                # and inline PRE.
                prev_text = None
                keep_leading_ws = True
            elif prev_text:
                # Drop protection if set previously.
                keep_leading_ws = False
        else:
            node = _remove(node)
            continue

        next_node = _next(prev, node, is_pre)
        prev = node
        node = next_node

    if prev_text:
        prev_text.data = _TRAILING_SPACE.sub("", prev_text.data)
        if not prev_text.data:
            _remove(prev_text)


def _remove(node):
    """Remove ``node`` from the DOM and return the next node in sequence."""
    following = node.nextSibling or node.parentNode
    node.parentNode.removeChild(node)
    return following


def _next(prev, current, is_pre):
    """Return the next node in sequence given the current and previous nodes."""
    if (prev and prev.parentNode is current) or is_pre(current):
        return current.nextSibling or current.parentNode
    return current.firstChild or current.nextSibling or current.parentNode
