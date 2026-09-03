# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. The layout is the
# dagre port (``domonic_libs.dagre``); mermaid's v3 "unified" rendering-util
# layer is not ported -- this emits shapes/edges over dagre's coordinates.
"""Render a parsed flowchart: lay out with dagre, draw to a domonic ``<svg>``."""

from __future__ import annotations

from domonic.svg import circle, defs, ellipse, g, marker, path, polygon, rect, style, svg, text

from ...dagre import Graph, layout
from ..text_metrics import calculate_text_dimensions
from .db import FlowDB

_PAD_X = 14
_PAD_Y = 10
_FONT = {"fontSize": 14}

_STYLE = """
text { font-family: "trebuchet ms", verdana, arial, sans-serif; font-size: 14px; fill: #333; }
.flow-node { fill: #ECECFF; stroke: #9370DB; stroke-width: 1px; }
.flow-edge { fill: none; stroke: #333; stroke-width: 1.5px; }
.flow-edge.thick { stroke-width: 3px; }
.flow-edge.dotted { stroke-dasharray: 3 3; }
.flow-edge.invisible { stroke: none; }
.edge-label { fill: #333; }
.edge-label-bg { fill: #ECECFF; opacity: 0.85; }
.cluster { fill: #ffffde; stroke: #aaaa33; stroke-width: 1px; }
.cluster-label { fill: #333; font-weight: bold; }
"""

_DIR_MAP = {"TD": "TB", "TB": "TB", "BT": "BT", "LR": "LR", "RL": "RL"}


def render_flowchart(db: FlowDB):
    rankdir = _DIR_MAP.get(db.direction, "TB")
    node_in_subgraph = {n: sg["id"] for sg in db.subgraphs for n in sg["nodes"]}

    graph = Graph({"multigraph": True, "compound": True})
    graph.setGraph({"rankdir": rankdir, "nodesep": 40, "ranksep": 50, "marginx": 8, "marginy": 8})
    graph.setDefaultEdgeLabel(lambda *a: {})

    for vid, node in db.vertices.items():
        dims = calculate_text_dimensions(node["text"], _FONT)
        w = dims["width"] + 2 * _PAD_X
        h = dims["height"] + 2 * _PAD_Y
        if node["shape"] in ("circle", "doublecircle"):
            w = h = max(w, h)
        elif node["shape"] == "diamond":
            w += dims["width"] * 0.6
            h += dims["height"] * 0.8
        graph.setNode(vid, {"width": w, "height": h, "label": node["text"], "shape": node["shape"]})

    for sg in db.subgraphs:
        graph.setNode(sg["id"], {"width": 0, "height": 0, "cluster": True, "label": sg["title"]})
        for n in sg["nodes"]:
            if graph.hasNode(n):
                graph.setParent(n, sg["id"])

    for i, e in enumerate(db.edges):
        label = {}
        if e["text"]:
            d = calculate_text_dimensions(e["text"], _FONT)
            label = {"width": d["width"] + 8, "height": d["height"] + 4, "labelpos": "c",
                     "minlen": e.get("length", 1)}
        else:
            label = {"minlen": e.get("length", 1)}
        graph.setEdge(e["start"], e["end"], label, f"e{i}")

    layout(graph)

    gl = graph.graph()
    root = svg(**{"class": "mermaid flowchart", "xmlns": "http://www.w3.org/2000/svg",
                  "viewBox": f"0 0 {round(gl['width'])} {round(gl['height'])}",
                  "width": str(round(gl["width"])), "height": str(round(gl["height"]))})
    root.appendChild(style(_STYLE))
    root.appendChild(_arrow_defs())

    # clusters first (behind)
    for sg in db.subgraphs:
        node = graph.node(sg["id"])
        if node.get("x") is None:
            continue
        x = node["x"] - node["width"] / 2
        y = node["y"] - node["height"] / 2
        grp = g(**{"class": "cluster-group"})
        grp.appendChild(rect(**{"x": x, "y": y, "width": node["width"], "height": node["height"],
                                "rx": 4, "class": "cluster"}))
        if sg["title"]:
            grp.appendChild(text(sg["title"], **{"x": node["x"], "y": y + 14,
                                                 "text-anchor": "middle", "class": "cluster-label"}))
        root.appendChild(grp)

    for i, e in enumerate(db.edges):
        edge = graph.edge(e["start"], e["end"], f"e{i}")
        pts = edge.get("points") or []
        if len(pts) < 2:
            continue
        cls = "flow-edge"
        if e["stroke"] == "thick":
            cls += " thick"
        elif e["stroke"] == "dotted":
            cls += " dotted"
        elif e["stroke"] == "invisible":
            cls += " invisible"
        d = "M " + " L ".join(f"{p['x']:.1f},{p['y']:.1f}" for p in pts)
        seg = path(d=d, **{"class": cls})
        if e["type"] in ("arrow_point", "double_arrow_point"):
            seg.setAttribute("marker-end", "url(#flow-arrow)")
        elif e["type"] in ("arrow_cross", "double_arrow_cross"):
            seg.setAttribute("marker-end", "url(#flow-cross)")
        elif e["type"] in ("arrow_circle", "double_arrow_circle"):
            seg.setAttribute("marker-end", "url(#flow-circle)")
        if e["type"].startswith("double_"):
            seg.setAttribute("marker-start", "url(#flow-arrow)")
        root.appendChild(seg)

        if e["text"] and edge.get("x") is not None:
            td = calculate_text_dimensions(e["text"], _FONT)
            root.appendChild(rect(**{"x": edge["x"] - td["width"] / 2 - 3, "y": edge["y"] - td["height"] / 2,
                                     "width": td["width"] + 6, "height": td["height"], "class": "edge-label-bg"}))
            root.appendChild(text(e["text"], **{"x": edge["x"], "y": edge["y"],
                                                "text-anchor": "middle", "dominant-baseline": "central",
                                                "class": "edge-label"}))

    for vid, node in db.vertices.items():
        gn = graph.node(vid)
        root.appendChild(_draw_shape(gn, node))

    return root


def _arrow_defs():
    return defs(
        marker(path(d="M 0 0 L 10 5 L 0 10 z", **{"fill": "#333"}),
               **{"id": "flow-arrow", "refX": 9, "refY": 5, "markerWidth": 10, "markerHeight": 10,
                  "orient": "auto", "markerUnits": "userSpaceOnUse"}),
        marker(path(d="M 1,1 L 9,9 M 9,1 L 1,9", **{"stroke": "#333", "stroke-width": "1.5", "fill": "none"}),
               **{"id": "flow-cross", "refX": 5, "refY": 5, "markerWidth": 10, "markerHeight": 10,
                  "orient": "auto", "markerUnits": "userSpaceOnUse"}),
        marker(circle(**{"cx": 5, "cy": 5, "r": 4, "fill": "#fff", "stroke": "#333"}),
               **{"id": "flow-circle", "refX": 9, "refY": 5, "markerWidth": 11, "markerHeight": 11,
                  "orient": "auto", "markerUnits": "userSpaceOnUse"}),
    )


def _draw_shape(gn, node):
    x, y = gn["x"], gn["y"]
    w, h = gn["width"], gn["height"]
    shape = node["shape"]
    grp = g(**{"class": "flow-node-group"})
    left, top = x - w / 2, y - h / 2

    if shape in ("circle", "doublecircle"):
        grp.appendChild(ellipse(**{"cx": x, "cy": y, "rx": w / 2, "ry": h / 2, "class": "flow-node"}))
        if shape == "doublecircle":
            grp.appendChild(ellipse(**{"cx": x, "cy": y, "rx": w / 2 - 4, "ry": h / 2 - 4,
                                       "class": "flow-node", "fill": "none"}))
    elif shape == "diamond":
        grp.appendChild(polygon(**{"points": f"{x},{top} {x + w / 2},{y} {x},{y + h / 2} {left},{y}",
                                   "class": "flow-node"}))
    elif shape == "hexagon":
        q = w / 5
        grp.appendChild(polygon(**{"points": (
            f"{left + q},{top} {left + w - q},{top} {left + w},{y} "
            f"{left + w - q},{y + h / 2} {left + q},{y + h / 2} {left},{y}"), "class": "flow-node"}))
    elif shape == "stadium":
        grp.appendChild(rect(**{"x": left, "y": top, "width": w, "height": h,
                                "rx": h / 2, "ry": h / 2, "class": "flow-node"}))
    elif shape in ("lean_right", "lean_left", "trapezoid", "inv_trapezoid"):
        sk = min(w / 4, 18)
        if shape == "lean_right":
            pts = f"{left + sk},{top} {left + w},{top} {left + w - sk},{y + h / 2} {left},{y + h / 2}"
        elif shape == "lean_left":
            pts = f"{left},{top} {left + w - sk},{top} {left + w},{y + h / 2} {left + sk},{y + h / 2}"
        elif shape == "trapezoid":
            pts = f"{left + sk},{top} {left + w - sk},{top} {left + w},{y + h / 2} {left},{y + h / 2}"
        else:
            pts = f"{left},{top} {left + w},{top} {left + w - sk},{y + h / 2} {left + sk},{y + h / 2}"
        grp.appendChild(polygon(**{"points": pts, "class": "flow-node"}))
    elif shape == "cylinder":
        ry = min(h / 6, 8)
        grp.appendChild(path(d=(
            f"M {left},{top + ry} A {w / 2},{ry} 0 0 0 {left + w},{top + ry} "
            f"L {left + w},{top + h - ry} A {w / 2},{ry} 0 0 1 {left},{top + h - ry} Z "
            f"M {left},{top + ry} A {w / 2},{ry} 0 0 1 {left + w},{top + ry}"), **{"class": "flow-node"}))
    elif shape == "odd":
        grp.appendChild(polygon(**{"points": (
            f"{left},{top} {left + w - 10},{top} {left + w},{y} {left + w - 10},{y + h / 2} {left},{y + h / 2}"),
            "class": "flow-node"}))
    else:  # square, round, subroutine
        rx = 0 if shape in ("square", "subroutine") else 6
        grp.appendChild(rect(**{"x": left, "y": top, "width": w, "height": h,
                                "rx": rx, "ry": rx, "class": "flow-node"}))
        if shape == "subroutine":
            grp.appendChild(rect(**{"x": left + 6, "y": top, "width": w - 12, "height": h,
                                    "class": "flow-node", "fill": "none"}))

    grp.appendChild(text(node["text"], **{"x": x, "y": y, "text-anchor": "middle",
                                          "dominant-baseline": "central"}))
    return grp
