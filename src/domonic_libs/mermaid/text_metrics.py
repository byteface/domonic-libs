# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Mirrors
# ``calculateTextDimensions`` / ``calculateTextWidth`` / ``calculateTextHeight``
# in src/utils.ts.
"""Off-DOM text measurement.

Mermaid sizes every label by appending a ``<text>`` element and reading
``.getBBox()``. domonic measures ``<text>`` off-DOM with bundled font metrics
(``Element.getBBox`` / ``getComputedTextLength``, added in domonic 1.5.0 after
this port surfaced the gap -- see ``docs/domonic-wrinkles.md``), so this is a
straight port: build a ``<text>``, set the font, read the box.

Like upstream it measures against both ``sans-serif`` and the configured family
and keeps the larger result (a diagram must not overflow if the user's font is
unavailable), splits on ``<br>`` and memoises on
``text + fontSize + fontWeight + fontFamily``.
"""

from __future__ import annotations

import re
from functools import lru_cache

from domonic.svg import svg as _svg, text as _text

from .common import _LINE_BREAK_RE

_ZERO_WIDTH_SPACE = "​"
_FONT_SIZE_RE = re.compile(r"([\d.]+)")


def parse_font_size(value) -> tuple[float, str]:
    """``utils.parseFontSize`` -- a number or a CSS length -> (px, "Npx")."""
    if value is None:
        return 12.0, "12px"
    if isinstance(value, (int, float)):
        return float(value), f"{value}px"
    match = _FONT_SIZE_RE.search(str(value))
    px = float(match.group(1)) if match else 12.0
    return px, f"{px}px"


def _measure_line(line: str, font_size_px: str, font_weight, font_family: str) -> tuple[float, float]:
    container = _svg()
    element = _text(line or _ZERO_WIDTH_SPACE)
    element.setAttribute(
        "style",
        f"font-size:{font_size_px};font-weight:{font_weight};font-family:{font_family}",
    )
    container.appendChild(element)
    box = element.getBBox()
    return box.width, box.height


@lru_cache(maxsize=2048)
def _dimensions(text: str, font_size, font_weight, font_family: str) -> dict:
    if not text:
        return {"width": 0, "height": 0, "lineHeight": 0}

    _, font_size_px = parse_font_size(font_size)
    lines = _LINE_BREAK_RE.split(text)

    results = []
    for family in ("sans-serif", font_family):
        width = 0.0
        height = 0
        line_height = 0
        for line in lines:
            w, h = _measure_line(line, font_size_px, font_weight, family)
            width = max(width, round(w))
            c_height = round(h)
            height += c_height
            line_height = max(line_height, c_height)
        results.append({"width": round(width), "height": height, "lineHeight": line_height})

    first, second = results
    bigger_first = (
        first["height"] > second["height"]
        and first["width"] > second["width"]
        and first["lineHeight"] > second["lineHeight"]
    )
    return first if bigger_first else second


def calculate_text_dimensions(text: str, config: dict | None = None) -> dict:
    config = config or {}
    return dict(
        _dimensions(
            text or "",
            config.get("fontSize", 12),
            config.get("fontWeight", 400),
            config.get("fontFamily", "Arial"),
        )
    )


def calculate_text_width(text: str, config: dict | None = None) -> int:
    return calculate_text_dimensions(text, config)["width"]


def calculate_text_height(text: str, config: dict | None = None) -> int:
    return calculate_text_dimensions(text, config)["height"]
