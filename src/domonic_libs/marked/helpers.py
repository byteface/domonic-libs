# Ported from markedjs/marked (MIT). Mirrors src/helpers.ts.
"""String helpers used by the tokenizer and renderer."""

from __future__ import annotations

import re
from urllib.parse import quote

from .rules import other

_ESCAPE_REPLACEMENTS = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
}


def escape_html_entities(html, encode=False):
    if encode:
        if other["escapeTest"].search(html):
            return other["escapeReplace"].sub(
                lambda m: _ESCAPE_REPLACEMENTS[m.group(0)], html
            )
    else:
        if other["escapeTestNoEncode"].search(html):
            return other["escapeReplaceNoEncode"].sub(
                lambda m: _ESCAPE_REPLACEMENTS[m.group(0)], html
            )
    return html


# encodeURI keeps these unescaped; `%` too (marked restores it after).
_ENCODE_URI_SAFE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.!~*'();/?:@&=+$,#%"


def clean_url(href):
    try:
        href = quote(href, safe=_ENCODE_URI_SAFE)
        href = other["percentDecode"].sub("%", href)
    except Exception:
        return None
    return href


def split_cells(table_row, count=None):
    # ensure that every cell-delimiting pipe has a space before it to
    # distinguish it from an escaped pipe
    def _pipe(match):
        offset = match.start()
        escaped = False
        curr = offset - 1
        while curr >= 0 and table_row[curr] == "\\":
            escaped = not escaped
            curr -= 1
        return "|" if escaped else " |"

    row = other["findPipe"].sub(_pipe, table_row)
    cells = other["splitPipe"].split(row)
    i = 0

    if not cells[0].strip():
        cells.pop(0)
    if cells and not cells[-1].strip():
        cells.pop()

    if count:
        if len(cells) > count:
            del cells[count:]
        else:
            while len(cells) < count:
                cells.append("")

    for i in range(len(cells)):
        cells[i] = other["slashPipe"].sub("|", cells[i].strip())
    return cells


def rtrim(string, c, invert=False):
    length = len(string)
    if length == 0:
        return ""

    suff_len = 0
    while suff_len < length:
        curr_char = string[length - suff_len - 1]
        if curr_char == c and not invert:
            suff_len += 1
        elif curr_char != c and invert:
            suff_len += 1
        else:
            break
    return string[: length - suff_len]


def trim_trailing_blank_lines(string):
    lines = string.split("\n")
    end = len(lines) - 1
    while end >= 0 and other["blankLine"].match(lines[end]):
        end -= 1
    if len(lines) - end <= 2:
        return string
    return "\n".join(lines[: end + 1])


def find_closing_bracket(string, b):
    if b[1] not in string:
        return -1
    level = 0
    i = 0
    while i < len(string):
        if string[i] == "\\":
            i += 1
        elif string[i] == b[0]:
            level += 1
        elif string[i] == b[1]:
            level -= 1
            if level < 0:
                return i
        i += 1
    if level > 0:
        return -2
    return -1


def expand_tabs(line, indent=0):
    col = indent
    expanded = []
    for char in line:
        if char == "\t":
            added = 4 - (col % 4)
            expanded.append(" " * added)
            col += added
        else:
            expanded.append(char)
            col += 1
    return "".join(expanded)
