# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Behaviourally
# mirrors src/diagrams/timeline/parser/timeline.jison.
"""Parser for the timeline grammar.

    timeline
    title <text>
    section <name>
    <period>            -- a task under the current section
    : <event>           -- appended to the previous task
    accTitle: / accDescr: / accDescr { }
"""

from __future__ import annotations

import re

from .db import TimelineDB

# The grammar tokenises a line into a leading ``period`` (text up to the first
# colon) and any number of ``: event`` chunks -- so ``2004 : Facebook : Google``
# is one task with two events. Split on a colon followed by whitespace.
_COLON_SPLIT = re.compile(r"\s*:\s+")


class ParseError(ValueError):
    pass


def parse(text: str, db: TimelineDB | None = None) -> TimelineDB:
    db = db or TimelineDB()
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    i = 0
    while i < len(lines) and (
        not lines[i].strip() or lines[i].strip().startswith(("%%", "#"))
    ):
        i += 1
    if i >= len(lines) or lines[i].split(None, 1)[0].lower() != "timeline":
        raise ParseError("expected 'timeline' header")
    i += 1

    while i < len(lines):
        raw = lines[i]
        i += 1
        line = raw.strip()
        if not line or line.startswith(("%%", "#")):
            continue

        lower = line.lower()
        if lower.startswith("title "):
            db.set_diagram_title(line[6:].strip())
        elif lower.startswith("acctitle:"):
            db.set_acc_title(line.split(":", 1)[1].strip())
        elif lower.startswith("accdescr:"):
            db.set_acc_description(line.split(":", 1)[1].strip())
        elif lower.startswith("accdescr") and "{" in line:
            chunk = [line.split("{", 1)[1]]
            while i < len(lines) and "}" not in chunk[-1]:
                chunk.append(lines[i])
                i += 1
            db.set_acc_description("\n".join(chunk).split("}", 1)[0].strip())
        elif lower.startswith("section "):
            db.add_section(line[8:].strip())
        else:
            parts = _COLON_SPLIT.split(line)
            period, events = parts[0].strip(), [p.strip() for p in parts[1:]]
            if period:
                # `add_task` takes the first event so the task is never empty.
                db.add_task(period, 0, events[0] if events else "")
                events = events[1:]
            for event in events:
                db.add_event(event)

    return db
