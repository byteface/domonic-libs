# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Mirrors
# src/diagrams/pie/pieRenderer.ts.
"""Render a parsed pie chart to a domonic ``<svg>`` tree.

Leans on domonic's ``d3.shape`` (``pie``, ``arc``) and ``d3.scale``
(``scaleOrdinal``) -- the d3 modules domonic 1.5.0 added -- and on
``d3.selection`` for building the tree, exactly as upstream does.

The 12-colour slice palette is a fixed approximation of mermaid's default theme
(the HSL-derived theme system is not ported); ``getBoundingClientRect`` for the
legend-width measurement is swapped for ``text_metrics``.
"""

from __future__ import annotations

from domonic.d3.scale import scaleOrdinal
from domonic.d3.selection import select
from domonic.d3.shape import arc, pie
from domonic.svg import style as _style, svg as _svg

from ..text_metrics import calculate_text_width
from .db import PieDB

_MARGIN = 40
_LEGEND_RECT_SIZE = 18
_LEGEND_SPACING = 4
_HEIGHT = 450
_TEXT_POSITION = 0.75  # config.pie.textPosition default

# Approximation of the default theme's computed pie1..pie12.
_PALETTE = [
    "#ECECFF", "#ffffde", "#4c4cb3", "#d4d4ff", "#b3b3a1", "#ccccb3",
    "#8080ce", "#3a3a8c", "#3a8c3a", "#8c8c3a", "#3a3a5c", "#5c8c3a",
]

# Trimmed port of ``diagrams/pie/pieStyles.ts`` with default-theme values.
_STYLE = """
text { font-family: "trebuchet ms", verdana, arial, sans-serif; }
.pieCircle { stroke: black; stroke-width: 2px; opacity: 0.7; }
.pieOuterCircle { stroke: black; stroke-width: 2px; fill: none; }
.pieTitleText { text-anchor: middle; font-size: 25px; fill: #333; }
.slice { fill: #333; font-size: 17px; }
.legend text { fill: #333; font-size: 17px; }
"""


def render_pie(db: PieDB):
    width = _HEIGHT
    radius = min(width, _HEIGHT) / 2 - _MARGIN

    root = _svg(**{"class": "mermaid pie", "xmlns": "http://www.w3.org/2000/svg"})
    root.appendChild(_style(_STYLE))
    sel = select(root)
    group = sel.append("g").attr(
        "transform", f"translate({width / 2},{_HEIGHT / 2})"
    )

    outer_stroke_width = 2
    group.append("circle").attr("cx", 0).attr("cy", 0).attr(
        "r", radius + outer_stroke_width / 2
    ).attr("class", "pieOuterCircle")

    sections = db.get_sections()
    data = sorted(
        ({"label": label, "value": value} for label, value in sections.items()),
        key=lambda d: d["value"],
        reverse=True,
    )
    arcs = pie().value(lambda d, *_: d["value"])(data)

    color = scaleOrdinal(_PALETTE)
    # d3's arc() reads angles from the datum; upstream relies on that default.
    # We wire the accessors explicitly so the wedges draw regardless.
    start = lambda d, *_: d["startAngle"]  # noqa: E731
    end = lambda d, *_: d["endAngle"]  # noqa: E731
    arc_gen = arc().innerRadius(0).outerRadius(radius).startAngle(start).endAngle(end)
    label_arc = (
        arc()
        .innerRadius(radius * _TEXT_POSITION)
        .outerRadius(radius * _TEXT_POSITION)
        .startAngle(start)
        .endAngle(end)
    )

    for datum in arcs:
        group.append("path").attr("d", arc_gen(datum)).attr(
            "fill", color(datum["data"]["label"])
        ).attr("class", "pieCircle")

    total = sum(sections.values()) or 1
    for datum in arcs:
        cx, cy = label_arc.centroid(datum)
        pct = f"{round(datum['data']['value'] / total * 100)}%"
        group.append("text").text(pct).attr(
            "transform", f"translate({cx},{cy})"
        ).attr("style", "text-anchor: middle").attr("class", "slice")

    title = db.get_diagram_title()
    if title:
        group.append("text").text(title).attr("x", 0).attr(
            "y", -(_HEIGHT - 50) / 2
        ).attr("class", "pieTitleText").attr("style", "text-anchor: middle")

    # -- legend --------------------------------------------------------
    domain = color.domain()
    legend_line_h = _LEGEND_RECT_SIZE + _LEGEND_SPACING
    offset = (legend_line_h * len(domain)) / 2
    horizontal = 12 * _LEGEND_RECT_SIZE
    longest = 0
    for index, label in enumerate(domain):
        vertical = index * legend_line_h - offset
        entry = group.append("g").attr("class", "legend").attr(
            "transform", f"translate({horizontal},{vertical})"
        )
        entry.append("rect").attr("width", _LEGEND_RECT_SIZE).attr(
            "height", _LEGEND_RECT_SIZE
        ).attr("style", f"fill: {color(label)}; stroke: {color(label)}")
        datum = next((a for a in arcs if a["data"]["label"] == label), None)
        text = label
        if datum is not None and db.get_show_data():
            text = f"{label} [{datum['data']['value']}]"
        entry.append("text").attr("x", _LEGEND_RECT_SIZE + _LEGEND_SPACING).attr(
            "y", _LEGEND_RECT_SIZE - _LEGEND_SPACING
        ).text(text)
        longest = max(longest, calculate_text_width(text, {"fontSize": 17}))

    total_width = width + _MARGIN + _LEGEND_RECT_SIZE + _LEGEND_SPACING + longest
    root.setAttribute("viewBox", f"0 0 {round(total_width)} {_HEIGHT}")
    root.setAttribute("width", str(round(total_width)))
    root.setAttribute("height", str(_HEIGHT))
    return root
