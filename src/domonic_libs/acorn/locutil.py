# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/locutil.js.
"""Line/column position helpers."""

from __future__ import annotations

from .whitespace import nextLineBreak


class Position:
    def __init__(self, line, col):
        self.line = line
        self.column = col

    def offset(self, n):
        return Position(self.line, self.column + n)

    def __repr__(self):  # pragma: no cover
        return f"{self.line}:{self.column}"


class SourceLocation:
    def __init__(self, p, start, end):
        self.start = start
        self.end = end
        if getattr(p, "sourceFile", None) is not None:
            self.source = p.sourceFile


def getLineInfo(inp, offset):
    line = 1
    cur = 0
    while True:
        nextBreak = nextLineBreak(inp, cur, offset)
        if nextBreak < 0:
            return Position(line, offset - cur)
        line += 1
        cur = nextBreak
