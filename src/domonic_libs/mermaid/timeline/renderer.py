# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Compresses
# src/diagrams/timeline/timelineRenderer.ts + svgDraw.js.
"""Render a parsed timeline to a domonic ``<svg>`` tree.

Faithful to mermaid's layout: a row of section nodes across the top, each with
its tasks (periods) below it, and each task's events stacked under a dashed
connector, all sitting above one horizontal activity line with an arrowhead.
Section / task colours cycle through a 12-entry palette (a fixed approximation
of the default theme's ``cScale0..11``).

Text wrapping uses ``text_metrics`` (mermaid wraps by ``getComputedTextLength``
on tspans; the result is the same).
"""

from __future__ import annotations

from domonic.svg import defs, g, line, marker, path, rect, style, svg, text, tspan

from ..text_metrics import calculate_text_width
from .db import TimelineDB

_LEFT_MARGIN = 50
_NODE_WIDTH = 150
_PADDING = 20
_FONT_SIZE = 14
_LINE_HEIGHT = _FONT_SIZE * 1.1
_TASK_STRIDE = 200

# Approximation of the default theme's cScale0..11.
_PALETTE = [
    "#ECECFF", "#ffffde", "#fff5ad", "#d1e0ff", "#ffe0b3", "#c9f2e4",
    "#e5d1ff", "#ffd6e0", "#d6ffd6", "#fff0c9", "#e0d1ff", "#d1fff0",
]

_STYLE = """
text { font-family: "trebuchet ms", verdana, arial, sans-serif; }
.timeline-node text { fill: #333; font-size: 14px; }
.timeline-title { fill: #333; font: 700 24px "trebuchet ms", sans-serif; }
.node-line { stroke: #333; stroke-width: 1px; }
.task-line { stroke: #999; stroke-width: 1px; stroke-dasharray: 4 2; }
.activity-line { stroke: #333; stroke-width: 3px; }
"""


def _wrap(content: str, width: int) -> list[str]:
    font = {"fontSize": _FONT_SIZE}
    lines: list[str] = []
    current: list[str] = []
    for word in content.split():
        current.append(word)
        if calculate_text_width(" ".join(current), font) > width and len(current) > 1:
            current.pop()
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines or [content]


def _node_height(content: str) -> float:
    n = len(_wrap(content, _NODE_WIDTH))
    return n * _LINE_HEIGHT + _FONT_SIZE * 1.1 * 0.5 + _PADDING


def _draw_node(descr: str, section: int, x: float, y: float, node_height: float):
    grp = g(**{"class": f"timeline-node section-{section % len(_PALETTE)}",
              "transform": f"translate({x},{y})"})
    width = _NODE_WIDTH + 2 * _PADDING
    rd = 5
    grp.appendChild(
        path(
            d=(f"M0 {node_height - rd} v{-node_height + 2 * rd} q0,-5 5,-5 "
               f"h{width - 2 * rd} q5,0 5,5 v{node_height - rd} H0 Z"),
            **{"class": "node-bkg", "fill": _PALETTE[section % len(_PALETTE)], "stroke": "#999"},
        )
    )
    grp.appendChild(
        line(**{"class": "node-line", "x1": 0, "y1": node_height, "x2": width, "y2": node_height})
    )
    lines = _wrap(descr, _NODE_WIDTH)
    label = text(
        **{"x": width / 2, "y": node_height / 2, "text-anchor": "middle",
           "dominant-baseline": "central"}
    )
    start_dy = -(_LINE_HEIGHT * (len(lines) - 1)) / 2
    for idx, ln in enumerate(lines):
        label.appendChild(
            tspan(ln, **{"x": width / 2, "dy": start_dy if idx == 0 else _LINE_HEIGHT})
        )
    grp.appendChild(label)
    return grp


def _arrow_defs():
    return defs(
        marker(
            path(d="M 0,0 V 4 L6,2 Z"),
            **{"id": "arrowhead", "refX": 5, "refY": 2, "markerWidth": 6,
               "markerHeight": 4, "orient": "auto"},
        )
    )


def render_timeline(db: TimelineDB):
    tasks = db.get_tasks()
    sections = db.get_sections()
    diagram_title = db.get_diagram_title()

    root = svg(**{"class": "mermaid timeline", "xmlns": "http://www.w3.org/2000/svg"})
    root.appendChild(style(_STYLE))
    root.appendChild(_arrow_defs())

    max_section_h = max(
        [_node_height(s) + 20 for s in sections], default=0
    )
    max_task_h = max([_node_height(t["task"]) + 20 for t in tasks], default=60)
    max_event_h = 0.0
    for task in tasks:
        run = sum(_node_height(e) for e in task["events"])
        if task["events"]:
            run += (len(task["events"]) - 1) * 10
        max_event_h = max(max_event_h, run)

    title_offset = 40 if diagram_title else 0
    master_y0 = 50 + title_offset
    master_x = _LEFT_MARGIN + 50
    color = 0
    max_x = master_x
    max_y = master_y0

    def draw_tasks(task_list, section_color, x0, y0, multicolor):
        nonlocal max_x, max_y
        x = x0
        c = section_color
        for task in task_list:
            th = max_task_h
            root.appendChild(_draw_node(task["task"], c, x, y0, th))
            events_bottom = y0 + th
            if task["events"]:
                ey = y0 + th + 40
                root.appendChild(
                    line(**{"class": "task-line", "x1": x + (_NODE_WIDTH + 2 * _PADDING) / 2,
                            "y1": y0 + th, "x2": x + (_NODE_WIDTH + 2 * _PADDING) / 2,
                            "y2": ey + max_event_h + 20, "marker-end": "url(#arrowhead)"})
                )
                for event in task["events"]:
                    eh = _node_height(event)
                    root.appendChild(_draw_node(event, c, x, ey, eh))
                    ey += eh + 10
                events_bottom = ey
            max_x = max(max_x, x + _NODE_WIDTH + 2 * _PADDING)
            max_y = max(max_y, events_bottom)
            x += _TASK_STRIDE
            if multicolor:
                c += 1
        return x

    if sections:
        for section_idx, section in enumerate(sections):
            in_section = [t for t in tasks if t["section"] == section]
            root.appendChild(_draw_node(section, section_idx, master_x, 50 + title_offset, max_section_h))
            draw_tasks(in_section, section_idx, master_x, master_y0 + max_section_h + 50, False)
            master_x += _TASK_STRIDE * max(len(in_section), 1)
            max_x = max(max_x, master_x)
    else:
        draw_tasks(tasks, 0, master_x, master_y0, True)

    # activity line + title
    depth_y = max_y + 40
    root.appendChild(
        line(**{"class": "activity-line", "x1": _LEFT_MARGIN, "y1": depth_y,
                "x2": max_x + _LEFT_MARGIN, "y2": depth_y, "marker-end": "url(#arrowhead)"})
    )
    if diagram_title:
        root.appendChild(
            text(diagram_title, **{"x": (max_x + _LEFT_MARGIN) / 2, "y": 24,
                                   "text-anchor": "middle", "class": "timeline-title"})
        )

    pad = 20
    total_w = max_x + _LEFT_MARGIN + pad
    total_h = depth_y + pad
    root.setAttribute("viewBox", f"0 0 {round(total_w)} {round(total_h)}")
    root.setAttribute("width", str(round(total_w)))
    root.setAttribute("height", str(round(total_h)))
    return root
