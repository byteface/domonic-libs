# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0.
"""Shared helpers -- ``sanitize_text`` and line-break handling.

Mirrors ``src/diagrams/common/common.ts``. Mermaid runs label text through
DOMPurify (twice, under the default ``strict`` security level); the port reuses
``domonic_libs.dompurify`` for that. Plain diagram text is unaffected.
"""

from __future__ import annotations

import re

from ..dompurify import DOMPurify

MERMAID_VERSION = "11.9.0"

_LINE_BREAK_RE = re.compile(r"<br\s*/?>", re.I)
_purifier = DOMPurify()


def get_rows(text: str | None) -> list[str]:
    if not text:
        return [""]
    processed = _break_to_placeholder(text).replace("\r\n", "\n").replace("\r", "\n")
    return processed.replace("#br#", "\n").split("\n")


def _break_to_placeholder(text: str) -> str:
    return _LINE_BREAK_RE.sub("#br#", text)


def _placeholder_to_break(text: str) -> str:
    return text.replace("#br#", "<br/>")


def remove_script(text: str) -> str:
    return _purifier.sanitize(text)


def _sanitize_more(text: str, config: dict) -> str:
    flowchart = config.get("flowchart") or {}
    if flowchart.get("htmlLabels") is not False:
        level = config.get("securityLevel", "strict")
        if level in ("antiscript", "strict"):
            text = remove_script(text)
        elif level != "loose":
            text = _break_to_placeholder(text)
            text = text.replace("<", "&lt;").replace(">", "&gt;")
            text = text.replace("=", "&equals;")
            text = _placeholder_to_break(text)
    return text


def sanitize_text(text: str, config: dict) -> str:
    if not text:
        return text
    return _purifier.sanitize(_sanitize_more(text, config), {"FORBID_TAGS": ["style"]})
