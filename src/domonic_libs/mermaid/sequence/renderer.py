# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Compresses
# src/diagrams/sequence/sequenceRenderer.ts + svgDraw.js -- see the note below.
"""Render a parsed sequence diagram to a domonic ``<svg>`` tree.

Faithful to mermaid's layout *model* -- the ``Bounds`` accumulator (including the
``sequence_items`` block stack whose members grow to enclose every ``insert``
with per-nesting-level margins), actor columns, the per-message vertical walk,
self-message curves, notes, activation bars, and the loop / alt / opt / par /
critical / break / rect box machinery. It emits mermaid's element/class
structure (``.actor``, ``.actor-line``, ``.messageText``, ``.messageLine0/1``,
``.note``/``.noteText``, ``.activation{0,1,2}``, ``.loopLine``/``.loopText``/
``.labelBox``, ``#arrowhead`` markers).

Measurement comes from ``text_metrics``, a straight port of mermaid's
``calculateTextDimensions`` over domonic's off-DOM ``getBBox()`` (domonic 1.5.0).

Not yet ported (``tests/test_mermaid.py`` KNOWN_GAPS): ``box`` participant
groups, autonumber badges, KaTeX, actor-link popups, the actor stick-figure
glyph (``actor`` participants render as a box), and label wrapping.
"""

from __future__ import annotations

from domonic.svg import defs, g, line, marker, path, rect, style, svg, text

from ..config import get_config
from ..text_metrics import calculate_text_dimensions
from .db import LINETYPE, PLACEMENT, SequenceDB

_DOTTED = {
    LINETYPE["DOTTED"], LINETYPE["DOTTED_CROSS"], LINETYPE["DOTTED_POINT"],
    LINETYPE["DOTTED_OPEN"], LINETYPE["BIDIRECTIONAL_DOTTED"],
}
_ARROW_END = {LINETYPE["SOLID"], LINETYPE["DOTTED"]}
_CROSS_END = {LINETYPE["SOLID_CROSS"], LINETYPE["DOTTED_CROSS"]}
_POINT_END = {LINETYPE["SOLID_POINT"], LINETYPE["DOTTED_POINT"]}
_BIDIRECTIONAL = {LINETYPE["BIDIRECTIONAL_SOLID"], LINETYPE["BIDIRECTIONAL_DOTTED"]}

# LINETYPE -> (loop-box label, is-background-rect)
_LOOP_END_LABEL = {
    LINETYPE["LOOP_END"]: ("loop", False),
    LINETYPE["ALT_END"]: ("alt", False),
    LINETYPE["OPT_END"]: ("opt", False),
    LINETYPE["PAR_END"]: ("par", False),
    LINETYPE["CRITICAL_END"]: ("critical", False),
    LINETYPE["BREAK_END"]: ("break", False),
    LINETYPE["RECT_END"]: (None, True),
}
_LOOP_START = {
    LINETYPE["LOOP_START"], LINETYPE["ALT_START"], LINETYPE["OPT_START"],
    LINETYPE["PAR_START"], LINETYPE["PAR_OVER_START"], LINETYPE["CRITICAL_START"],
    LINETYPE["BREAK_START"], LINETYPE["RECT_START"],
}
_LOOP_SECTION = {
    LINETYPE["ALT_ELSE"], LINETYPE["PAR_AND"], LINETYPE["CRITICAL_OPTION"],
}


def _dget(obj, key, default=None):
    value = obj.get(key, default)
    return default if value is None else value


# A trimmed port of ``diagrams/sequence/styles.js`` with the default theme's
# values baked in -- enough that a rendered ``<svg>`` is legible on its own.
_STYLE = """
text { font-family: "trebuchet ms", verdana, arial, sans-serif; }
.actor { font-size: 14px; }
.messageText { fill: #333; font-size: 16px; }
.loopText, .labelText { fill: #333; font-size: 14px; }
.noteText { fill: #333; font-size: 14px; }
.loopLine { stroke-dasharray: 2, 2; }
"""


class Bounds:
    """Mirrors the ``bounds`` accumulator in ``sequenceRenderer.ts``."""

    def __init__(self, conf):
        self.conf = conf
        self.data = {"startx": None, "starty": None, "stopx": None, "stopy": None}
        self.vertical_pos = 0
        self.sequence_items: list[dict] = []
        self.activations: list[dict] = []

    @staticmethod
    def _upd(obj, key, value, fn):
        obj[key] = value if obj.get(key) is None else fn(value, obj[key])

    def update_bounds(self, startx, starty, stopx, stopy):
        box_margin = self.conf["boxMargin"]
        counter = 0

        def update_item(item, is_activation):
            nonlocal counter
            counter += 1
            n = len(self.sequence_items) - counter + 1
            self._upd(item, "starty", starty - n * box_margin, min)
            self._upd(item, "stopy", stopy + n * box_margin, max)
            self._upd(self.data, "startx", startx - n * box_margin, min)
            self._upd(self.data, "stopx", stopx + n * box_margin, max)
            if not is_activation:
                self._upd(item, "startx", startx - n * box_margin, min)
                self._upd(item, "stopx", stopx + n * box_margin, max)
                self._upd(self.data, "starty", starty - n * box_margin, min)
                self._upd(self.data, "stopy", stopy + n * box_margin, max)

        for it in self.sequence_items:
            update_item(it, False)
        for it in self.activations:
            update_item(it, True)

    def insert(self, startx, starty, stopx, stopy):
        x1, x2 = min(startx, stopx), max(startx, stopx)
        y1, y2 = min(starty, stopy), max(starty, stopy)
        self._upd(self.data, "startx", x1, min)
        self._upd(self.data, "starty", y1, min)
        self._upd(self.data, "stopx", x2, max)
        self._upd(self.data, "stopy", y2, max)
        self.update_bounds(x1, y1, x2, y2)

    def bump_vertical_pos(self, amount):
        self.vertical_pos += amount
        self._upd(self.data, "stopy", self.vertical_pos, max)

    def get_vertical_pos(self):
        return self.vertical_pos

    def new_loop(self, title=None, fill=None):
        title = title or {}
        self.sequence_items.append(
            {
                "startx": None, "starty": self.vertical_pos, "stopx": None, "stopy": None,
                "title": title.get("message"), "wrap": title.get("wrap"),
                "width": title.get("width"), "height": 0, "fill": fill,
                "sections": None, "sectionTitles": None,
            }
        )

    def end_loop(self):
        return self.sequence_items.pop()

    def add_section_to_loop(self, message):
        loop = self.sequence_items.pop()
        loop["sections"] = loop["sections"] or []
        loop["sectionTitles"] = loop["sectionTitles"] or []
        loop["sections"].append({"y": self.vertical_pos, "height": 0})
        loop["sectionTitles"].append(message)
        self.sequence_items.append(loop)


def _font(conf, prefix):
    return {
        "fontFamily": conf[f"{prefix}FontFamily"],
        "fontSize": conf[f"{prefix}FontSize"],
        "fontWeight": conf[f"{prefix}FontWeight"],
    }


def _actor_center(actor):
    return actor["x"] + actor["width"] / 2


def _calculate_actor_margins(actor_keys, actors, messages, conf):
    """Widen the gap between adjacent actors so their messages fit (approx)."""
    index = {key: i for i, key in enumerate(actor_keys)}
    extra = [0.0] * max(len(actor_keys) - 1, 0)
    msg_font = _font(conf, "message")
    for message in messages:
        src, dst = message.get("from"), message.get("to")
        if not isinstance(src, str) or not isinstance(dst, str):
            continue
        if src not in index or dst not in index or src == dst:
            continue
        lo, hi = sorted((index[src], index[dst]))
        span = hi - lo
        if span <= 0:
            continue
        label = message.get("message") or ""
        width = calculate_text_dimensions(label, msg_font)["width"] + 2 * conf["wrapPadding"]
        need = width - span * conf["width"]
        if need > 0:
            per_gap = need / span
            for gap in range(lo, hi):
                extra[gap] = max(extra[gap], per_gap)
    return extra


def _adjust_loop_height_for_wrap(bounds, message, pre_margin, post_margin, add_fn, conf):
    bounds.bump_vertical_pos(pre_margin)
    height_adjust = post_margin
    if message.get("message"):
        text = message["message"]
        text = text.get("text") if isinstance(text, dict) else text
        if text:
            dims = calculate_text_dimensions(f"[{text}]", _font(conf, "message"))
            height_adjust = post_margin + max(dims["height"], conf["labelBoxHeight"])
    add_fn(message)
    bounds.bump_vertical_pos(height_adjust)


def _loop_title(message):
    # By the time a block statement reaches the renderer, ``db.add_signal`` has
    # flattened its label onto ``message["message"]`` (a string).
    text = message.get("message")
    if isinstance(text, dict):
        text = text.get("text")
    return {"message": text, "wrap": message.get("wrap"), "width": message.get("width")}


def render_sequence(db: SequenceDB):
    conf = get_config()["sequence"]
    actors = db.get_actors()
    actor_keys = db.get_actor_keys()
    messages = db.get_messages()

    root = svg(**{"class": "mermaid sequence", "xmlns": "http://www.w3.org/2000/svg"})
    root.appendChild(style(_STYLE))
    root.appendChild(_arrow_defs())

    bounds = Bounds(conf)
    diagram_title = db.get_diagram_title()
    title_offset = 30 if diagram_title else 0
    if diagram_title:
        bounds.bump_vertical_pos(title_offset)

    # -- position actor columns ------------------------------------------
    margins = _calculate_actor_margins(actor_keys, actors, messages, conf)
    x = conf["diagramMarginX"]
    for i, key in enumerate(actor_keys):
        actor = actors[key]
        actor["width"] = conf["width"]
        actor["height"] = conf["height"]
        actor["x"] = x
        actor["starty"] = bounds.get_vertical_pos()
        bounds.insert(actor["x"], bounds.get_vertical_pos(), actor["x"] + actor["width"], actor["height"])
        gap = conf["actorMargin"] + (margins[i] if i < len(margins) else 0)
        x += actor["width"] + gap

    for key in actor_keys:
        root.appendChild(_draw_actor(actors[key], conf, footer=False))
    bounds.bump_vertical_pos(conf["height"])

    # -- walk messages --------------------------------------------------
    activations: list[dict] = []
    box_margin = conf["boxMargin"]
    box_text_margin = conf["boxTextMargin"]

    for message in messages:
        mtype = message.get("type")

        if mtype == LINETYPE["NOTE"]:
            _draw_note(root, message, actors, conf, bounds)
        elif mtype == LINETYPE["ACTIVE_START"]:
            actor = actors[message["from"]]
            depth = _active_depth(activations, message["from"])
            activations.append(
                {"actor": message["from"], "startx": _actor_center(actor),
                 "starty": bounds.get_vertical_pos() + 2, "depth": depth}
            )
        elif mtype == LINETYPE["ACTIVE_END"]:
            for act in reversed(activations):
                if act["actor"] == message["from"] and "stopy" not in act:
                    act["stopy"] = bounds.get_vertical_pos()
                    root.appendChild(_draw_activation(act, conf))
                    bounds.insert(act["startx"] - 5, act["starty"], act["startx"] + 5, act["stopy"])
                    break
        elif mtype == LINETYPE["AUTONUMBER"]:
            visible = (message.get("message") or {}).get("visible")
            if visible:
                db.enable_sequence_numbers()
            elif visible is False:
                db.disable_sequence_numbers()
        elif mtype in _LOOP_START:
            pre = box_margin
            post = box_margin + box_text_margin
            fill = None
            if mtype == LINETYPE["RECT_START"]:
                post = box_margin
                fill = _loop_title(message)["message"]
                _adjust_loop_height_for_wrap(bounds, message, pre, post,
                                             lambda m, f=fill: bounds.new_loop(None, f), conf)
            else:
                _adjust_loop_height_for_wrap(bounds, message, pre, post,
                                             lambda m: bounds.new_loop(_loop_title(m)), conf)
        elif mtype in _LOOP_SECTION:
            _adjust_loop_height_for_wrap(
                bounds, message, box_margin + box_text_margin, box_margin,
                lambda m: bounds.add_section_to_loop(_loop_title(m)), conf,
            )
        elif mtype in _LOOP_END_LABEL:
            label, is_rect = _LOOP_END_LABEL[mtype]
            loop_model = bounds.end_loop()
            root.appendChild(_draw_loop(loop_model, label, conf, is_rect))
            bounds.bump_vertical_pos(loop_model["stopy"] - bounds.get_vertical_pos())
        else:
            _draw_message(root, message, actors, conf, bounds)

    # -- footer (mirrored actors) -------------------------------------
    if conf["mirrorActors"]:
        bounds.bump_vertical_pos(conf["boxMargin"] * 2)
        for key in actor_keys:
            actor = actors[key]
            actor["stopy"] = bounds.get_vertical_pos()
            root.appendChild(_draw_actor(actor, conf, footer=True))
        bounds.bump_vertical_pos(conf["height"] + conf["boxMargin"])

    # -- lifelines (under everything but defs) -----------------------
    life_bottom = bounds.get_vertical_pos() - (
        conf["height"] + conf["boxMargin"] if conf["mirrorActors"] else 0
    )
    # sit the lifelines right after <style> + <defs>, under the actor groups
    anchor = root.childNodes[2] if len(root.childNodes) > 2 else None
    for key in actor_keys:
        actor = actors[key]
        cx = _actor_center(actor)
        root.insertBefore(
            line(**{"x1": cx, "y1": actor["starty"] + actor["height"], "x2": cx, "y2": life_bottom,
                    "class": "actor-line", "stroke": "#999", "stroke-width": "0.5px", "name": actor["name"]}),
            anchor,
        )

    # -- viewBox ----------------------------------------------------
    pad = conf["diagramMarginX"]
    data = bounds.data
    min_x = _dget(data, "startx", 0) - pad
    min_y = _dget(data, "starty", 0) - conf["diagramMarginY"] - title_offset
    width = _dget(data, "stopx", 0) - min_x + pad
    height = _dget(data, "stopy", 0) - min_y + conf["diagramMarginY"]
    root.setAttribute("viewBox", f"{round(min_x)} {round(min_y)} {round(width)} {round(height)}")
    root.setAttribute("width", str(round(width)))
    root.setAttribute("height", str(round(height)))

    if diagram_title:
        root.appendChild(
            text(diagram_title, **{"x": round(min_x + width / 2), "y": round(min_y + 14),
                                   "class": "messageText", "text-anchor": "middle", "font-weight": "bold"})
        )
    return root


# -- drawing primitives (svgDraw.js) ------------------------------------


def _arrow_defs():
    return defs(
        marker(
            path(d="M 0 0 L 10 5 L 0 10 z"),
            **{"id": "arrowhead", "refX": 7.9, "refY": 5, "markerUnits": "userSpaceOnUse",
               "markerWidth": 12, "markerHeight": 12, "orient": "auto"},
        ),
        marker(
            path(d="M 0 0 L 10 5 L 0 10 L 4 5 z"),
            **{"id": "filled-head", "refX": 8, "refY": 5, "markerWidth": 20, "markerHeight": 28, "orient": "auto"},
        ),
        marker(
            path(d="M 1,2 L 6,7 M 6,2 L 1,7"),
            **{"id": "crosshead", "refX": 4, "refY": 5, "markerWidth": 15, "markerHeight": 8, "orient": "auto",
               "stroke": "#000000", "stroke-width": "1pt", "fill": "none"},
        ),
    )


def _draw_actor(actor, conf, footer):
    y = actor["stopy"] if footer else actor["starty"]
    cls = "actor " + ("actor-bottom" if footer else "actor-top")
    cx = actor["x"] + actor["width"] / 2
    h = actor["height"]
    grp = g(**{"class": "actor"})

    if actor.get("type") == "actor":
        # Stick figure -- an approximation of svgDraw.drawActorTypeActor.
        stroke = {"stroke": "#666", "stroke-width": "2", "fill": "none"}
        r = 7
        grp.appendChild(rect(**{"x": cx - r, "y": y + 2, "width": r * 2, "height": r * 2,
                                "rx": r, "ry": r, "fill": "#eaeaea", "stroke": "#666", "class": cls,
                                "name": actor["name"]}))
        grp.appendChild(line(**{"x1": cx, "y1": y + 2 + r * 2, "x2": cx, "y2": y + h - 22, **stroke}))
        grp.appendChild(line(**{"x1": cx - 14, "y1": y + 22, "x2": cx + 14, "y2": y + 22, **stroke}))
        grp.appendChild(line(**{"x1": cx, "y1": y + h - 22, "x2": cx - 12, "y2": y + h - 6, **stroke}))
        grp.appendChild(line(**{"x1": cx, "y1": y + h - 22, "x2": cx + 12, "y2": y + h - 6, **stroke}))
        grp.appendChild(text(str(actor["description"]),
                             **{"x": cx, "y": y + h + 12, "text-anchor": "middle", "class": "actor"}))
        return grp

    grp.appendChild(
        rect(**{"x": actor["x"], "y": y, "width": actor["width"], "height": h,
                "rx": 3, "ry": 3, "fill": "#eaeaea", "stroke": "#666", "class": cls, "name": actor["name"]})
    )
    grp.appendChild(
        text(str(actor["description"]),
             **{"x": cx, "y": y + h / 2,
                "text-anchor": "middle", "dominant-baseline": "central", "class": "actor"})
    )
    return grp


def _draw_activation(act, conf):
    depth = act.get("depth", 0)
    half = conf["activationWidth"] / 2
    return rect(
        **{"x": act["startx"] - half + depth * conf["activationWidth"], "y": act["starty"],
           "width": conf["activationWidth"], "height": max(act["stopy"] - act["starty"], 1),
           "fill": "#f4f4f4", "stroke": "#666", "class": f"activation{depth % 3}"}
    )


def _active_depth(activations, actor):
    return sum(1 for a in activations if a["actor"] == actor and "stopy" not in a)


def _draw_loop(loop_model, label, conf, is_rect):
    sx, sy = loop_model["startx"], loop_model["starty"]
    ex, ey = loop_model["stopx"], loop_model["stopy"]
    if sx is None or ex is None:
        sx, ex = 0, 0
    grp = g(**{"class": "loop"})

    if is_rect:
        grp.appendChild(
            rect(**{"x": sx, "y": sy, "width": max(ex - sx, 0), "height": max(ey - sy, 0),
                    "class": "rect", "fill": loop_model.get("fill") or "#ececff", "stroke": "none"})
        )
        return grp

    def loop_line(x1, y1, x2, y2, dashed=False):
        attrs = {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "class": "loopLine",
                 "stroke": "#666", "fill": "none"}
        if dashed:
            attrs["stroke-dasharray"] = "3, 3"
        return line(**attrs)

    grp.appendChild(loop_line(sx, sy, ex, sy))
    grp.appendChild(loop_line(ex, sy, ex, ey))
    grp.appendChild(loop_line(sx, ey, ex, ey))
    grp.appendChild(loop_line(sx, sy, sx, ey))
    for section in loop_model.get("sections") or []:
        grp.appendChild(loop_line(sx, section["y"], ex, section["y"], dashed=True))

    lbw = conf["labelBoxWidth"]
    lbh = conf["labelBoxHeight"]
    grp.appendChild(
        path(
            d=(f"M {sx},{sy} L {sx + lbw},{sy} L {sx + lbw},{sy + lbh - 7} "
               f"L {sx + lbw - 8.4},{sy + lbh} L {sx},{sy + lbh} Z"),
            **{"class": "labelBox", "fill": "#ececff", "stroke": "#666"},
        )
    )
    grp.appendChild(
        text(label, **{"x": round(sx + lbw / 2), "y": round(sy + lbh / 2),
                       "text-anchor": "middle", "dominant-baseline": "central", "class": "labelText"})
    )
    if loop_model.get("title"):
        grp.appendChild(
            text(str(loop_model["title"]),
                 **{"x": round(sx + lbw / 2 + (ex - sx) / 2), "y": round(sy + conf["boxMargin"] + conf["boxTextMargin"]),
                    "text-anchor": "middle", "dominant-baseline": "central", "class": "loopText"})
        )
    for i, section in enumerate(loop_model.get("sections") or []):
        titles = loop_model.get("sectionTitles") or []
        section_title = titles[i].get("message") if i < len(titles) and isinstance(titles[i], dict) else None
        if section_title:
            grp.appendChild(
                text(str(section_title),
                     **{"x": round(sx + (ex - sx) / 2),
                        "y": round(section["y"] + conf["boxMargin"] + conf["boxTextMargin"]),
                        "text-anchor": "middle", "dominant-baseline": "central", "class": "loopText"})
            )
    return grp


def _draw_message(root, message, actors, conf, bounds):
    src = actors[message["from"]]
    dst = actors[message["to"]]
    msg_text = message.get("message") or ""
    if isinstance(msg_text, dict):
        msg_text = msg_text.get("text") or ""
    dims = calculate_text_dimensions(msg_text, _font(conf, "message"))

    bounds.bump_vertical_pos(10)
    bounds.bump_vertical_pos(dims["height"])

    self_message = message["from"] == message["to"]
    total_offset = dims["height"] - 10 + conf["boxMargin"]
    line_start_y = bounds.get_vertical_pos() + total_offset

    startx = _actor_center(src)
    stopx = _actor_center(dst)
    if self_message:
        loop_w = max(dims["width"] / 2, conf["width"] / 2)
        root.appendChild(
            path(
                d=(f"M {startx},{line_start_y} C {startx + 60},{line_start_y - 10} "
                   f"{startx + 60},{line_start_y + 30} {startx},{line_start_y + 20}"),
                **{"class": "messageLine0", "stroke-width": "2", "stroke": "#333", "fill": "none",
                   "marker-end": "url(#arrowhead)"},
            )
        )
        text_x = startx + loop_w / 2
        total_offset += 30
    else:
        seg = line(
            **{"x1": startx, "y1": line_start_y, "x2": stopx, "y2": line_start_y,
               "stroke-width": "2", "stroke": "#333", "fill": "none",
               "class": "messageLine1" if message["type"] in _DOTTED else "messageLine0"},
        )
        if message["type"] in _DOTTED:
            seg.setAttribute("stroke-dasharray", "3, 3")
        if message["type"] in _ARROW_END:
            seg.setAttribute("marker-end", "url(#arrowhead)")
        elif message["type"] in _POINT_END:
            seg.setAttribute("marker-end", "url(#filled-head)")
        elif message["type"] in _CROSS_END:
            seg.setAttribute("marker-end", "url(#crosshead)")
        elif message["type"] in _BIDIRECTIONAL:
            seg.setAttribute("marker-end", "url(#arrowhead)")
            seg.setAttribute("marker-start", "url(#arrowhead)")
        root.appendChild(seg)
        text_x = (startx + stopx) / 2
        total_offset += 30

    root.appendChild(
        text(msg_text, **{"x": round(text_x), "y": round(line_start_y - 5),
                          "text-anchor": "middle", "class": "messageText"})
    )

    bounds.bump_vertical_pos(total_offset)
    dx = max(dims["width"] / 2, conf["width"] / 2)
    bounds.insert(min(startx, stopx) - dx, line_start_y - 10, max(startx, stopx) + dx, bounds.get_vertical_pos())


def _draw_note(root, message, actors, conf, bounds):
    bounds.bump_vertical_pos(conf["boxMargin"])
    placement = message.get("placement")
    actor_ref = message["from"]
    if isinstance(actor_ref, list):
        a, b = actors[actor_ref[0]], actors[actor_ref[-1]]
        startx = a["x"]
        width = (b["x"] + b["width"]) - a["x"]
    else:
        actor = actors[actor_ref]
        width = conf["width"]
        if placement == PLACEMENT["LEFTOF"]:
            startx = actor["x"] - width - conf["boxMargin"]
        elif placement == PLACEMENT["RIGHTOF"]:
            startx = actor["x"] + actor["width"] + conf["boxMargin"]
        else:
            startx = actor["x"] + actor["width"] / 2 - width / 2

    msg = message.get("message") or ""
    if isinstance(msg, dict):
        msg = msg.get("text") or ""
    dims = calculate_text_dimensions(msg, _font(conf, "note"))
    height = dims["height"] + 2 * conf["noteMargin"]
    starty = bounds.get_vertical_pos()

    grp = g()
    grp.appendChild(
        rect(**{"x": startx, "y": starty, "width": width, "height": height,
                "fill": "#EDF2AE", "stroke": "#aaaa33", "class": "note"})
    )
    grp.appendChild(
        text(msg, **{"x": round(startx + width / 2), "y": round(starty + height / 2),
                     "text-anchor": "middle", "dominant-baseline": "central", "class": "noteText"})
    )
    root.appendChild(grp)

    bounds.bump_vertical_pos(height)
    bounds.insert(startx, starty, startx + width, starty + height)
