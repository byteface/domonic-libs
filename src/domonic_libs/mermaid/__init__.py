# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Preserve the
# upstream licence when redistributing.
"""A Python port of Mermaid -- text to diagram, straight to a domonic SVG tree.

Status: **sequence diagrams, parser + database only.** The renderer (and the
domonic SVG / text-metrics work it drives) is next. Flowcharts need a dagre
port first.

    from domonic_libs.mermaid.sequence import parse
    db = parse('''sequenceDiagram
        Alice->>Bob: Hi
        Bob-->>Alice: Hey''')
    db.get_messages()   # the parsed message list

This port is a forcing function for domonic's SVG/CSSOM/geometry layer as much
as it is a diagram tool -- gaps get logged in ``docs/domonic-wrinkles.md``.
"""

from __future__ import annotations

from .common import MERMAID_VERSION
from .config import get_config, reset_config, set_config

__all__ = [
    "MERMAID_VERSION", "get_config", "set_config", "reset_config",
    "render", "render_element", "detect_type",
]

_DETECTORS = {
    "sequenceDiagram": "sequence",
    "pie": "pie",
    "timeline": "timeline",
    "flowchart": "flowchart",
    "graph": "flowchart",
}


def detect_type(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("%%", "#")):
            continue
        first = stripped.split(None, 1)[0]
        if first in _DETECTORS:
            return _DETECTORS[first]
        break
    raise ValueError(
        "could not detect a supported diagram type "
        "(sequenceDiagram, pie, timeline, flowchart/graph)"
    )


def render_element(text: str):
    """Parse ``text`` and return a domonic ``<svg>`` element."""
    kind = detect_type(text)
    if kind == "sequence":
        from .sequence import parse, render_sequence

        return render_sequence(parse(text))
    if kind == "pie":
        from .pie import parse, render_pie

        return render_pie(parse(text))
    if kind == "timeline":
        from .timeline import parse, render_timeline

        return render_timeline(parse(text))
    if kind == "flowchart":
        from .flowchart import parse, render_flowchart

        return render_flowchart(parse(text))
    raise ValueError(f"unsupported diagram type: {kind}")


def render(text: str) -> str:
    """Parse ``text`` and return the SVG markup as a string."""
    return str(render_element(text))
