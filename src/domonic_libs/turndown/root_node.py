# Ported from mixmark-io/turndown (MIT). Mirrors src/root-node.js.
"""Build the collapsed root node the converter walks."""

from __future__ import annotations

from .collapse_whitespace import collapse_whitespace
from .html_parser import parse_html
from .utilities import is_block, is_void, node_name


def root_node(input_value, options):
    if not isinstance(input_value, str):
        # turndown.js clones the node here. domonic nodes built programmatically
        # store their text children as plain ``str`` rather than Text nodes, and
        # the whitespace collapser walks real nodes -- so serialise and re-parse
        # instead. See docs/domonic-wrinkles.md.
        input_value = _to_html(input_value)

    root = parse_html(input_value)

    collapse_whitespace(
        {
            "element": root,
            "isBlock": is_block,
            "isVoid": is_void,
            "isPre": _is_pre_or_code if options.get("preformattedCode") else None,
        }
    )
    return root


def _is_pre_or_code(node):
    return node_name(node) in ("PRE", "CODE")


def _to_html(node):
    outer = getattr(node, "outerHTML", None)
    if outer:
        return outer
    # document / fragment: concatenate the serialised children
    children = getattr(node, "childNodes", None)
    if children:
        return "".join(str(child) for child in children)
    return str(node)
