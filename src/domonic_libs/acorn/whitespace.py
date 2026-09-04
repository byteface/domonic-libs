# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/whitespace.js.
# Preserve the upstream licence when redistributing.
"""Line-break and whitespace patterns used by the tokenizer.

The patterns are handed to ``domonic.javascript.RegExp`` in their exact JS
spelling (``\\u2028``, ``[^]`` to match any char including newlines, the global
flag, ``lastIndex`` scanning), so this module doubles as a probe of how
faithfully that RegExp shim mirrors JS regex syntax.
"""

from __future__ import annotations

from domonic.javascript import RegExp

# /\r\n?|\n| | /  -- a whole line break (CRLF counts as one).
lineBreak = RegExp("\\r\\n?|\\n|\\u2028|\\u2029")
lineBreakG = RegExp(lineBreak.source, "g")


def isNewLine(code):
    return code == 10 or code == 13 or code == 0x2028 or code == 0x2029


def nextLineBreak(code, frm, end=None):
    if end is None:
        end = len(code)
    for i in range(frm, end):
        nxt = ord(code[i])
        if isNewLine(nxt):
            if i < end - 1 and nxt == 13 and ord(code[i + 1]) == 10:
                return i + 2
            return i + 1
    return -1


# /[  -   　﻿]/
nonASCIIwhitespace = RegExp("[\\u1680\\u2000-\\u200a\\u202f\\u205f\\u3000\\ufeff]")

# /(?:\s|\/\/.*|\/\*[^]*?\*\/)*/g
skipWhiteSpace = RegExp("(?:\\s|\\/\\/.*|\\/\\*[^]*?\\*\\/)*", "g")
