# Ported from mixmark-io/turndown-plugin-gfm (MIT). Preserve the upstream
# licence when redistributing. Mirrors the plugin's src/ files.
"""GitHub Flavored Markdown rules for :class:`TurndownService`.

Usage mirrors turndown.js::

    from domonic_libs.turndown import TurndownService
    from domonic_libs.turndown.gfm import gfm

    service = TurndownService()
    service.use(gfm)                      # everything
    # or pick rules: service.use([strikethrough, tables])
"""

from __future__ import annotations

import re

from .utilities import node_name

_HIGHLIGHT_RE = re.compile(r"highlight-(?:text|source)-([a-z0-9]+)")


def strikethrough(turndown_service):
    turndown_service.add_rule(
        "strikethrough",
        {
            "filter": ["del", "s", "strike"],
            "replacement": lambda content, node, options: "~" + content + "~",
        },
    )


def task_list_items(turndown_service):
    turndown_service.add_rule(
        "taskListItems",
        {
            "filter": lambda node, options: (
                getattr(node, "type", None) == "checkbox"
                and node_name(node.parentNode) == "LI"
            ),
            "replacement": lambda content, node, options: (
                "[x] " if getattr(node, "checked", False) else "[ ] "
            ),
        },
    )


def highlighted_code_block(turndown_service):
    def _filter(node, options):
        first_child = node.firstChild
        return (
            node_name(node) == "DIV"
            and bool(_HIGHLIGHT_RE.search(node.getAttribute("class") or ""))
            and first_child
            and node_name(first_child) == "PRE"
        )

    def _replacement(content, node, options):
        class_name = node.getAttribute("class") or ""
        match = _HIGHLIGHT_RE.search(class_name)
        language = match.group(1) if match else ""
        return (
            "\n\n" + options["fence"] + language + "\n"
            + node.firstChild.textContent
            + "\n" + options["fence"] + "\n\n"
        )

    turndown_service.add_rule(
        "highlightedCodeBlock", {"filter": _filter, "replacement": _replacement}
    )


# -- tables -----------------------------------------------------------------

_ALIGN_MAP = {"left": ":--", "right": "--:", "center": ":-:"}


def _rows(table):
    return list(table.getElementsByTagName("tr"))


def _cell(content, node):
    index = list(node.parentNode.childNodes).index(node)
    prefix = "| " if index == 0 else " "
    return prefix + content + " |"


def _is_first_tbody(element):
    previous = element.previousSibling
    return node_name(element) == "TBODY" and (
        not previous
        or (
            node_name(previous) == "THEAD"
            and bool(re.match(r"\s*\Z", previous.textContent or "", re.IGNORECASE))
        )
    )


def _is_heading_row(tr):
    if tr is None:
        return False
    parent = tr.parentNode
    return node_name(parent) == "THEAD" or (
        parent.firstChild is tr
        and (node_name(parent) == "TABLE" or _is_first_tbody(parent))
        and all(node_name(child) == "TH" for child in tr.childNodes)
    )


def _table_cell(content, node, options):
    return _cell(content, node)


def _table_row(content, node, options):
    border_cells = ""
    if _is_heading_row(node):
        for child in node.childNodes:
            border = "---"
            align = (child.getAttribute("align") or "").lower()
            if align:
                border = _ALIGN_MAP.get(align, border)
            border_cells += _cell(border, child)
    return "\n" + content + ("\n" + border_cells if border_cells else "")


def _is_table(node, options):
    rows = _rows(node)
    return node_name(node) == "TABLE" and _is_heading_row(rows[0] if rows else None)


def _table(content, node, options):
    content = content.replace("\n\n", "\n", 1)  # ensure there are no blank lines
    return "\n\n" + content + "\n\n"


_TABLE_RULES = {
    "tableCell": {"filter": ["th", "td"], "replacement": _table_cell},
    "tableRow": {"filter": "tr", "replacement": _table_row},
    "table": {"filter": _is_table, "replacement": _table},
    "tableSection": {
        "filter": ["thead", "tbody", "tfoot"],
        "replacement": lambda content, node, options: content,
    },
}


def tables(turndown_service):
    def _keep_plain_tables(node, options):
        rows = _rows(node)
        return node_name(node) == "TABLE" and not _is_heading_row(
            rows[0] if rows else None
        )

    turndown_service.keep(_keep_plain_tables)
    for key, rule in _TABLE_RULES.items():
        turndown_service.add_rule(key, rule)


def gfm(turndown_service):
    turndown_service.use([highlighted_code_block, strikethrough, tables, task_list_items])
