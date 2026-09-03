# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Behaviourally
# covers the common subset of src/diagrams/flowchart/parser/flow.jison.
"""Flowchart parser.

mermaid's ``flow.jison`` is ~630 lines with a dozen lexer states; a full port is
out of scope, so this is a pragmatic scanner for the syntax people actually
write: a ``graph`` / ``flowchart`` header with an optional direction, node
shapes, the arrow zoo (``-->`` ``---`` ``-.->`` ``==>`` ``--x`` ``--o``,
lengths, ``-->|label|`` and ``-- label -->``), ``&`` groups, node chains, and
``subgraph`` / ``end``. Styling, ``click``, and markdown labels are skipped.
"""

from __future__ import annotations

import re

from .db import FlowDB

_HEADER_RE = re.compile(r"^(?:graph|flowchart)(?:\s+(TB|TD|BT|RL|LR))?\s*:?\s*$", re.I)

# Node id, then optionally a shape wrapper. Longest delimiters first.
_SHAPES = [
    (re.compile(r"^\(\(\((.*?)\)\)\)"), "doublecircle"),
    (re.compile(r"^\(\((.*?)\)\)"), "circle"),
    (re.compile(r"^\(\[(.*?)\]\)"), "stadium"),
    (re.compile(r"^\[\[(.*?)\]\]"), "subroutine"),
    (re.compile(r"^\[\((.*?)\)\]"), "cylinder"),
    (re.compile(r"^\{\{(.*?)\}\}"), "hexagon"),
    (re.compile(r"^\[/(.*?)\\\]"), "trapezoid"),
    (re.compile(r"^\[\\(.*?)/\]"), "inv_trapezoid"),
    (re.compile(r"^\[/(.*?)/\]"), "lean_right"),
    (re.compile(r"^\[\\(.*?)\\\]"), "lean_left"),
    (re.compile(r"^\{(.*?)\}"), "diamond"),
    (re.compile(r"^\[(.*?)\]"), "square"),
    (re.compile(r"^\((.*?)\)"), "round"),
    (re.compile(r"^>(.*?)\]"), "odd"),
]
_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]+")

# A *complete* link -- the dash/eq/dot run must end in a terminator char, so a
# bare "-- " (the start of a "-- label -->" edge) does not match here.
_LINK_RE = re.compile(
    r"""^\s*
        (?P<tail>[<xo])?
        (?P<body>-{2,}[-xo>]|={2,}[=xo>]|-?\.+-[xo>]?|~{3,})
        (?:\|(?P<label>[^|]*)\|)?
        \s*""",
    re.X,
)
_START_LINK_RE = re.compile(r"^\s*(?P<tail>[<xo])?(?P<body>--|==|-\.)\s")
# same body, un-anchored -- to locate the closing link of a "-- text --" edge.
_LINK_SEARCH_RE = re.compile(r"(?:-{2,}[-xo>]|={2,}[=xo>]|-?\.+-[xo>]?)")


class ParseError(ValueError):
    pass


def parse(text: str, db: FlowDB | None = None) -> FlowDB:
    db = db or FlowDB()
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    idx = 0
    while idx < len(lines) and (not lines[idx].strip() or lines[idx].strip().startswith("%%")):
        idx += 1
    if idx >= len(lines):
        raise ParseError("empty flowchart")
    header = _HEADER_RE.match(lines[idx].strip())
    if not header:
        raise ParseError(f"expected a 'graph' / 'flowchart' header, got {lines[idx]!r}")
    if header.group(1):
        db.set_direction(header.group(1))
    idx += 1

    stack: list[dict] = []  # open subgraphs
    statements: list[str] = []
    for raw in lines[idx:]:
        line = raw.split("%%", 1)[0]
        for part in line.split(";"):
            part = part.strip()
            if part:
                statements.append(part)

    for stmt in statements:
        low = stmt.lower()
        if low.startswith("title "):
            db.set_diagram_title(stmt[6:].strip())
        elif low.startswith("acctitle:"):
            db.set_acc_title(stmt.split(":", 1)[1])
        elif low.startswith("accdescr:"):
            db.set_acc_description(stmt.split(":", 1)[1])
        elif low.startswith("direction "):
            direction = stmt.split(None, 1)[1].strip()
            if stack:
                stack[-1]["direction"] = direction
            else:
                db.set_direction(direction)
        elif low.startswith("subgraph"):
            rest = stmt[len("subgraph"):].strip()
            sid, title = _parse_subgraph_head(rest)
            stack.append({"id": sid, "title": title, "nodes": []})
        elif low == "end":
            if stack:
                sg = stack.pop()
                db.add_subgraph(sg["id"], sg["nodes"], sg["title"])
                if stack:
                    stack[-1]["nodes"].append(sg["id"] or f"subGraph{len(db.subgraphs) - 1}")
        elif low.startswith(("style ", "classdef ", "class ", "linkstyle ", "click ")):
            continue
        else:
            touched = _parse_statement(stmt, db)
            if stack:
                stack[-1]["nodes"].extend(touched)

    return db


def _parse_subgraph_head(rest: str):
    m = re.match(r"^([A-Za-z0-9_.\-]+)?\s*(?:\[(.*?)\])?\s*$", rest)
    if m:
        return (m.group(1) or ""), (m.group(2) or m.group(1) or "")
    return "", rest.strip()


def _parse_node(s: str):
    """Consume one node token (id + optional shape) from the front of ``s``."""
    m = _ID_RE.match(s)
    if not m:
        return None
    vid = m.group(0)
    rest = s[m.end():]
    for pattern, shape in _SHAPES:
        sm = pattern.match(rest)
        if sm:
            return vid, sm.group(1).strip().strip('"'), shape, rest[sm.end():]
    return vid, None, None, rest


def _destruct_end_link(body: str, tail: str = ""):
    """``body`` is the full link run (``-->``, ``---``, ``--x``, ``==>`` ...)."""
    head = body[-1] if body and body[-1] in "xo>" else ""
    core = body[:-1] if head else body

    if "." in body:
        stroke = "dotted"
    elif "=" in body:
        stroke = "thick"
    elif "~" in body:
        stroke = "invisible"
    else:
        stroke = "normal"

    if head == "x" or tail == "x":
        etype = "arrow_cross"
    elif head == "o" or tail == "o":
        etype = "arrow_circle"
    elif head == ">" or tail == "<":
        etype = "arrow_point"
    else:
        etype = "arrow_open"
    if tail and head and etype != "arrow_open":
        etype = "double_" + etype

    if stroke == "dotted":
        length = max(body.count("."), 1)
    else:
        length = max(len([c for c in core if c in "-="]) - 1, 1)
    return {"type": etype, "stroke": stroke, "length": length}


def _parse_statement(stmt: str, db: FlowDB):
    touched: list[str] = []
    s = stmt
    prev_group: list[str] | None = None

    while s:
        node = _parse_node(s)
        if not node:
            break
        group = [node[0]]
        db.add_vertex(node[0], node[1], node[2])
        touched.append(node[0])
        s = node[3].lstrip()

        # '&' extends the current node group
        while s.startswith("&"):
            s = s[1:].lstrip()
            nxt = _parse_node(s)
            if not nxt:
                break
            group.append(nxt[0])
            db.add_vertex(nxt[0], nxt[1], nxt[2])
            touched.append(nxt[0])
            s = nxt[3].lstrip()

        if prev_group is not None:
            db.add_link(prev_group, group, pending_link, pending_text)  # noqa: F821

        if not s:
            break

        # "-- text --" style: START_LINK, then label, then the closing LINK.
        pending_text = ""
        lm = _LINK_RE.match(s)
        sm = _START_LINK_RE.match(s)
        if lm is None and sm is not None:
            after = s[sm.end():]
            close = _LINK_SEARCH_RE.search(after)
            if not close:
                break
            pending_text = after[: close.start()].strip()
            lm = _LINK_RE.match(after[close.start():])
            tail = sm.group("tail") or lm.group("tail") or ""
            body = lm.group("body")
            s = after[close.start() + lm.end():].lstrip()
        elif lm is not None:
            tail = lm.group("tail") or ""
            body = lm.group("body")
            pending_text = (lm.group("label") or "").strip()
            s = s[lm.end():].lstrip()
        else:
            break

        pending_link = _destruct_end_link(body, tail)
        prev_group = group

    return touched
