# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Behaviourally
# mirrors src/diagrams/sequence/parser/sequenceDiagram.jison.
"""A hand-written recursive-descent parser for the sequence-diagram grammar.

Mermaid generates its parser from a Jison grammar at build time (needing a Node
toolchain), so the port re-expresses the same grammar as Python. Every
production emits the exact statement dict the ``.jison`` semantic action does
(``{"type": "addMessage", ...}`` etc.), and ``SequenceDB.apply`` consumes the
nested ``document`` list identically -- so the two stay diffable at that seam.

Not yet handled (tracked in ``tests/test_mermaid.py`` KNOWN_GAPS): the stick /
reverse-dotted arrow family, ``()`` central connections, ``box`` sections,
``links``/``properties``/``details`` JSON, and ``@{ }`` participant config.
"""

from __future__ import annotations

import re

from .db import LINETYPE, PLACEMENT, SequenceDB

# Arrow tokens, longest first so `-->>` wins over `->`.
_ARROWS: list[tuple[str, int]] = [
    ("<<-->>", LINETYPE["BIDIRECTIONAL_DOTTED"]),
    ("<<->>", LINETYPE["BIDIRECTIONAL_SOLID"]),
    ("-->>", LINETYPE["DOTTED"]),
    ("->>", LINETYPE["SOLID"]),
    ("--x", LINETYPE["DOTTED_CROSS"]),
    ("-x", LINETYPE["SOLID_CROSS"]),
    ("--)", LINETYPE["DOTTED_POINT"]),
    ("-)", LINETYPE["SOLID_POINT"]),
    ("-->", LINETYPE["DOTTED_OPEN"]),
    ("->", LINETYPE["SOLID_OPEN"]),
]

_COMMENT_RE = re.compile(r"^\s*(?:#|%%)")
_BLOCK_OPENERS = {"loop", "opt", "rect", "break"}
_ALT_LIKE = {"alt", "par", "par_over", "critical"}
_SECTION_KEYWORDS = {"else", "and", "option", "end"}


class ParseError(ValueError):
    pass


def parse(text: str, db: SequenceDB | None = None) -> SequenceDB:
    db = db or SequenceDB()
    lines = _logical_lines(text)

    start = 0
    while start < len(lines) and (lines[start] == "" or _COMMENT_RE.match(lines[start])):
        start += 1
    if start >= len(lines) or lines[start].split(None, 1)[0].lower() != "sequencediagram":
        raise ParseError("expected 'sequenceDiagram' header")

    document, _ = _parse_document(lines, start + 1, db)
    db.apply(document)
    return db


# --------------------------------------------------------------------------


def _logical_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        # ';' is a NEWLINE token in the grammar.
        for part in raw.split(";"):
            out.append(part.strip())
    return out


def _first_word(line: str) -> str:
    return line.split(None, 1)[0].lower() if line else ""


def _rest_of_line(line: str, keyword: str) -> str:
    return line[len(keyword):].strip()


def _parse_document(lines, i, db, stop=_SECTION_KEYWORDS):
    """Grammar ``document`` -- lines until a section keyword or EOF."""
    document: list = []
    while i < len(lines):
        line = lines[i]
        if line == "" or _COMMENT_RE.match(line):
            i += 1
            continue
        if _first_word(line) in stop:
            break
        stmt, i = _parse_statement(lines, i, db)
        if stmt:
            document.append(stmt)
    return document, i


def _parse_statement(lines, i, db):
    line = lines[i]
    word = _first_word(line)

    if word in ("participant", "actor"):
        draw = "participant" if word == "participant" else "actor"
        return _parse_participant(_rest_of_line(line, word), draw), i + 1
    if word == "create":
        stmt = _parse_participant_statement(_rest_of_line(line, "create"))
        stmt["type"] = "createParticipant"
        return stmt, i + 1
    if word == "destroy":
        return {"type": "destroyParticipant", "actor": _rest_of_line(line, "destroy")}, i + 1

    if word == "activate":
        return {"type": "activeStart", "signalType": LINETYPE["ACTIVE_START"], "actor": _rest_of_line(line, "activate")}, i + 1
    if word == "deactivate":
        return {"type": "activeEnd", "signalType": LINETYPE["ACTIVE_END"], "actor": _rest_of_line(line, "deactivate")}, i + 1

    if word == "autonumber":
        return _parse_autonumber(line), i + 1

    if word == "note":
        return _parse_note(line, db), i + 1

    if word in ("title", "title:"):
        rest = line.split(":", 1)[1].strip() if word == "title:" else _rest_of_line(line, "title")
        db.set_diagram_title(rest)
        return None, i + 1
    if word == "acctitle:":
        db.set_acc_title(line.split(":", 1)[1].strip())
        return None, i + 1
    if word == "accdescr:":
        db.set_acc_description(line.split(":", 1)[1].strip())
        return None, i + 1

    if word in _BLOCK_OPENERS:
        return _parse_block(lines, i, db, word)
    if word in _ALT_LIKE:
        return _parse_alt_like(lines, i, db, word)

    return _parse_signal(line, db), i + 1


def _parse_participant_statement(spec: str):
    """``participant_statement`` -- optional ``participant`` / ``actor`` keyword."""
    spec = spec.strip()
    head = spec.split(None, 1)[0].lower() if spec else ""
    if head in ("participant", "actor"):
        return _parse_participant(spec[len(head):].strip(), "participant" if head == "participant" else "actor")
    return _parse_participant(spec, "participant")


def _parse_participant(spec: str, draw):
    spec = spec.strip()
    match = re.match(r"^(.*?)\s+as\s+(.+)$", spec, re.I)
    if match:
        actor = match.group(1).strip()
        return {"type": "addParticipant", "actor": actor, "draw": draw,
                "description": {"text": match.group(2).strip(), "type": draw}}
    return {"type": "addParticipant", "actor": spec, "draw": draw}


def _parse_autonumber(line: str):
    tokens = line.split()[1:]
    if tokens and tokens[0].lower() == "off":
        return {"type": "sequenceIndex", "sequenceVisible": False, "signalType": LINETYPE["AUTONUMBER"]}
    if len(tokens) >= 2:
        return {"type": "sequenceIndex", "sequenceIndex": float(tokens[0]), "sequenceIndexStep": float(tokens[1]),
                "sequenceVisible": True, "signalType": LINETYPE["AUTONUMBER"]}
    if len(tokens) == 1:
        return {"type": "sequenceIndex", "sequenceIndex": float(tokens[0]), "sequenceIndexStep": 1,
                "sequenceVisible": True, "signalType": LINETYPE["AUTONUMBER"]}
    return {"type": "sequenceIndex", "sequenceVisible": True, "signalType": LINETYPE["AUTONUMBER"]}


def _parse_note(line: str, db):
    body = _rest_of_line(line, "note")
    text_part = ""
    if ":" in body:
        body, text_part = body.split(":", 1)
    body = body.strip()
    text = db.parse_message(text_part.strip())

    m = re.match(r"^(left of|right of|over)\s+(.+)$", body, re.I)
    if not m:
        raise ParseError(f"bad note: {line!r}")
    placement_word, actors_part = m.group(1).lower(), m.group(2).strip()

    if placement_word == "over":
        names = [a.strip() for a in actors_part.split(",")]
        if len(names) == 1:
            names = [names[0], names[0]]
        return [{"type": "addParticipant", "actor": n} for n in dict.fromkeys(names)] + [
            {"type": "addNote", "placement": PLACEMENT["OVER"], "actor": names[:2], "text": text}
        ]
    placement = PLACEMENT["LEFTOF"] if placement_word == "left of" else PLACEMENT["RIGHTOF"]
    return [
        {"type": "addParticipant", "actor": actors_part},
        {"type": "addNote", "placement": placement, "actor": actors_part, "text": text},
    ]


def _parse_signal(line: str, db):
    left, _, msg = line.partition(":")
    for token, signal_type in _ARROWS:
        idx = left.find(token)
        if idx == -1:
            continue
        source = left[:idx].strip()
        target = left[idx + len(token):].strip()
        activate = deactivate = False
        if target.startswith("()"):
            raise ParseError("central connection '()' not yet supported")
        if target.startswith("+"):
            activate = True
            target = target[1:].strip()
        elif target.startswith("-"):
            deactivate = True
            target = target[1:].strip()
        parsed_msg = db.parse_message(msg.strip())

        stmts = [
            {"type": "addParticipant", "actor": source},
            {"type": "addParticipant", "actor": target},
            {"type": "addMessage", "from": source, "to": target, "signalType": signal_type,
             "msg": parsed_msg, "activate": activate},
        ]
        if activate:
            stmts.append({"type": "activeStart", "signalType": LINETYPE["ACTIVE_START"], "actor": target})
        elif deactivate:
            stmts.append({"type": "activeEnd", "signalType": LINETYPE["ACTIVE_END"], "actor": source})
        return stmts
    raise ParseError(f"not a signal: {line!r}")


def _parse_block(lines, i, db, word):
    rest = _rest_of_line(lines[i], word)
    inner, j = _parse_document(lines, i + 1, db, stop={"end"})
    if j >= len(lines) or _first_word(lines[j]) != "end":
        raise ParseError(f"unterminated '{word}' block")
    kind = {"loop": "LOOP", "opt": "OPT", "rect": "RECT", "break": "BREAK"}[word]
    text_key = {"loop": "loopText", "opt": "optText", "rect": "color", "break": "breakText"}[word]
    start = {"type": f"{word}Start", text_key: db.parse_message(rest), "signalType": LINETYPE[f"{kind}_START"]}
    end = {"type": f"{word}End", text_key: db.parse_message(rest) if word != "loop" else rest,
           "signalType": LINETYPE[f"{kind}_END"]}
    return [start] + inner + [end], j + 1


def _parse_alt_like(lines, i, db, word):
    rest = _rest_of_line(lines[i], word)
    section_word, kind = {
        "alt": ("else", "ALT"),
        "par": ("and", "PAR"),
        "par_over": ("and", "PAR"),
        "critical": ("option", "CRITICAL"),
    }[word]

    body: list = []
    j = i + 1
    while True:
        chunk, j = _parse_document(lines, j, db, stop={section_word, "end"})
        body += chunk
        if j >= len(lines):
            raise ParseError(f"unterminated '{word}' block")
        head = _first_word(lines[j])
        if head == "end":
            break
        if head == section_word:
            sec_text = _rest_of_line(lines[j], section_word)
            if word == "alt":
                body.append({"type": "else", "altText": db.parse_message(sec_text), "signalType": LINETYPE["ALT_ELSE"]})
            elif word in ("par", "par_over"):
                body.append({"type": "and", "parText": db.parse_message(sec_text), "signalType": LINETYPE["PAR_AND"]})
            else:
                body.append({"type": "option", "optionText": db.parse_message(sec_text),
                             "signalType": LINETYPE["CRITICAL_OPTION"]})
            j += 1

    start_type = "parStart" if word == "par_over" else f"{word.split('_')[0]}Start"
    start_signal = LINETYPE["PAR_OVER_START"] if word == "par_over" else LINETYPE[f"{kind}_START"]
    text_key = {"alt": "altText", "par": "parText", "par_over": "parText", "critical": "criticalText"}[word]
    start = {"type": start_type, text_key: db.parse_message(rest), "signalType": start_signal}
    end_type = f"{word.split('_')[0]}End"
    end = {"type": end_type, "signalType": LINETYPE[f"{kind}_END"]}
    return [start] + body + [end], j + 1
