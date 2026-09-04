# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/node.js.
"""AST node objects and the start/finish helpers.

``Node`` is a plain attribute bag (acorn's nodes are plain objects). ``to_dict``
walks it into nested dicts/lists -- an ESTree-shaped structure that is easy to
inspect and to hand to a JSX -> domonic transform later.
"""

from __future__ import annotations

from .locutil import SourceLocation

_SCALAR = (str, int, float, bool, type(None))


class Node:
    def __init__(self, parser, pos, loc):
        self.type = ""
        self.start = pos
        self.end = 0
        if parser.options["locations"]:
            self.loc = SourceLocation(parser, loc, None)
        if parser.options["directSourceFile"]:
            self.sourceFile = parser.options["directSourceFile"]
        if parser.options["ranges"]:
            self.range = [pos, 0]

    def to_dict(self):
        return _to_dict(self)

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<Node {self.type} {self.start}..{self.end}>"


def _to_dict(value):
    if isinstance(value, Node):
        out = {}
        for k, v in vars(value).items():
            if k == "loc":
                continue
            out[k] = _to_dict(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_to_dict(v) for v in value]
    return value


class NodeMixin:
    def startNode(self):
        return Node(self, self.start, self.startLoc)

    def startNodeAt(self, pos, loc):
        return Node(self, pos, loc)

    def _finishNodeAt(self, node, type, pos, loc):
        node.type = type
        node.end = pos
        if self.options["locations"]:
            node.loc.end = loc
        if self.options["ranges"]:
            node.range[1] = pos
        return node

    def finishNode(self, node, type):
        return self._finishNodeAt(node, type, self.lastTokEnd, self.lastTokEndLoc)

    def finishNodeAt(self, node, type, pos, loc):
        return self._finishNodeAt(node, type, pos, loc)

    def copyNode(self, node):
        newNode = Node(self, node.start, self.startLoc)
        for prop, val in vars(node).items():
            setattr(newNode, prop, val)
        return newNode
