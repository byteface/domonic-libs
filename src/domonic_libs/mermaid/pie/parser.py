# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Behaviourally
# mirrors the Langium `pie` grammar in @mermaid-js/parser.
"""Parser for the pie-chart grammar.

Mermaid 11 parses pie with Langium (a TypeScript language-server framework that
does not transpile), so the port re-expresses its small grammar directly:

    pie [showData] [title <text>]
        %% comment
        "label" : <non-negative number>
        accTitle: <text>
        accDescr: <text>  |  accDescr { <text> }
"""

from __future__ import annotations

import re

from .db import PieDB

_HEADER_RE = re.compile(r"^pie(?:\s+(showData))?(?:\s+title\s+(.+))?\s*$", re.I)
_SECTION_RE = re.compile(r'^"((?:[^"\\]|\\.)*)"\s*:\s*(-?\d+(?:\.\d+)?)\s*$')


class ParseError(ValueError):
    pass


def parse(text: str, db: PieDB | None = None) -> PieDB:
    db = db or PieDB()
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith(("%%", "#"))):
        i += 1
    if i >= len(lines):
        raise ParseError("empty pie definition")

    header = _HEADER_RE.match(lines[i].strip())
    if not header:
        raise ParseError(f"expected a 'pie' header, got {lines[i]!r}")
    if header.group(1):
        db.set_show_data(True)
    if header.group(2):
        db.set_diagram_title(header.group(2).strip())
    i += 1

    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith(("%%", "#")):
            continue

        lower = line.lower()
        if lower.startswith("acctitle:") or lower.startswith("acctitle :"):
            db.set_acc_title(line.split(":", 1)[1].strip())
            continue
        if lower.startswith("accdescr:") or lower.startswith("accdescr :"):
            db.set_acc_description(line.split(":", 1)[1].strip())
            continue
        if lower.startswith("accdescr") and "{" in line:
            chunk = [line.split("{", 1)[1]]
            while i < len(lines) and "}" not in chunk[-1]:
                chunk.append(lines[i])
                i += 1
            db.set_acc_description("\n".join(chunk).split("}", 1)[0].strip())
            continue
        if lower.startswith("title "):
            db.set_diagram_title(line[6:].strip())
            continue

        section = _SECTION_RE.match(line)
        if not section:
            raise ParseError(f"bad pie line: {line!r}")
        value = float(section.group(2))
        if value < 0:
            raise ParseError(f"pie values must be non-negative: {line!r}")
        label = section.group(1).replace('\\"', '"')
        if label in ("__proto__", "constructor", "prototype"):
            raise ParseError(f"unsafe section label: {label!r}")
        db.add_section(label, int(value) if value.is_integer() else value)

    return db
