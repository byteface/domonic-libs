# Ported from dagrejs/dagre (MIT). Mirrors lib/layout.ts (the ``runLayout`` /
# ``buildLayoutGraph`` / ``updateInputGraph`` core -- per-cluster ``rankdir``
# recursion is not ported).
"""``layout(graph)`` -- the dagre pipeline.

Runs on a graphlib ``Graph`` whose nodes carry ``width``/``height`` and whose
edges may carry ``minlen``/``weight``/``label{width,height}``. After ``layout``
each node has ``x``/``y`` (centre) and the graph label has ``width``/``height``;
each edge label has a ``points`` polyline.
"""

from __future__ import annotations

import math

from . import acyclic, coordinate_system, nesting_graph, normalize
from .add_border_segments import add_border_segments
from .graphlib import Graph
from .order import order
from .parent_dummy_chains import parent_dummy_chains
from .position import position
from .rank import rank
from .util import (
    add_dummy_node,
    as_non_compound_graph,
    build_layer_matrix,
    intersect_rect,
    map_values,
    normalize_ranks,
    pick,
    remove_empty_ranks,
)

_INF = math.inf

_GRAPH_NUM_ATTRS = ["nodesep", "edgesep", "ranksep", "marginx", "marginy"]
_GRAPH_DEFAULTS = {"ranksep": 50, "edgesep": 20, "nodesep": 50, "rankdir": "tb", "rankalign": "center"}
_GRAPH_ATTRS = ["acyclicer", "ranker", "rankdir", "align", "rankalign"]
_NODE_NUM_ATTRS = ["width", "height", "rank"]
_NODE_DEFAULTS = {"width": 0, "height": 0}
_EDGE_NUM_ATTRS = ["minlen", "weight", "width", "height", "labeloffset"]
_EDGE_DEFAULTS = {"minlen": 1, "weight": 1, "width": 0, "height": 0, "labeloffset": 10, "labelpos": "r"}
_EDGE_ATTRS = ["labelpos"]


def layout(g, opts=None):
    layout_g = _build_layout_graph(g)
    _run_layout(layout_g, opts or {})
    _update_input_graph(g, layout_g)
    return g


def _canonicalize(attrs):
    out = {}
    for k, v in (attrs or {}).items():
        out[k.lower() if isinstance(k, str) else k] = v
    return out


def _select_number_attrs(obj, attrs):
    return map_values(pick(obj, attrs), lambda v, k: float(v))


def _build_layout_graph(input_graph):
    g = Graph({"multigraph": True, "compound": True})
    graph = _canonicalize(input_graph.graph() or {})
    g.setGraph({**_GRAPH_DEFAULTS, **_select_number_attrs(graph, _GRAPH_NUM_ATTRS), **pick(graph, _GRAPH_ATTRS)})

    for v in input_graph.nodes():
        node = _canonicalize(input_graph.node(v))
        new_node = _select_number_attrs(node, _NODE_NUM_ATTRS)
        for k, dv in _NODE_DEFAULTS.items():
            new_node.setdefault(k, dv)
        g.setNode(v, new_node)
        parent = input_graph.parent(v)
        if parent is not None:
            g.setParent(v, parent)

    for e in input_graph.edges():
        edge = _canonicalize(input_graph.edge(e))
        g.setEdge(
            e,
            {**_EDGE_DEFAULTS, **_select_number_attrs(edge, _EDGE_NUM_ATTRS), **pick(edge, _EDGE_ATTRS)},
        )
    return g


def _run_layout(g, opts):
    _make_space_for_edge_labels(g)
    _remove_self_edges(g)
    acyclic.run(g, None)
    nesting_graph.run(g)
    rank(as_non_compound_graph(g))
    _inject_edge_label_proxies(g)
    remove_empty_ranks(g)
    nesting_graph.cleanup(g)
    normalize_ranks(g)
    _assign_rank_min_max(g)
    _remove_edge_label_proxies(g)
    normalize.run(g)
    parent_dummy_chains(g)
    add_border_segments(g)
    order(g, opts)
    _insert_self_edges(g)
    coordinate_system.adjust(g)
    position(g)
    _position_self_edges(g)
    _remove_border_nodes(g)
    normalize.undo(g)
    _fixup_edge_label_coords(g)
    coordinate_system.undo(g)
    _translate_graph(g)
    _assign_node_intersects(g)
    _reverse_points_for_reversed_edges(g)
    acyclic.undo(g)


def _update_input_graph(input_graph, layout_graph):
    for v in input_graph.nodes():
        input_label = input_graph.node(v)
        layout_label = layout_graph.node(v)
        if input_label is not None:
            input_label["x"] = layout_label.get("x")
            input_label["y"] = layout_label.get("y")
            input_label["order"] = layout_label.get("order")
            input_label["rank"] = layout_label.get("rank")
            if layout_graph.children(v):
                input_label["width"] = layout_label.get("width")
                input_label["height"] = layout_label.get("height")

    for e in input_graph.edges():
        input_label = input_graph.edge(e)
        layout_label = layout_graph.edge(e)
        input_label["points"] = layout_label.get("points")
        if "x" in layout_label:
            input_label["x"] = layout_label["x"]
            input_label["y"] = layout_label["y"]

    input_graph.graph()["width"] = layout_graph.graph().get("width")
    input_graph.graph()["height"] = layout_graph.graph().get("height")


# -- pipeline steps ------------------------------------------------


def _make_space_for_edge_labels(g):
    graph = g.graph()
    graph["ranksep"] /= 2
    for e in g.edges():
        edge = g.edge(e)
        edge["minlen"] *= 2
        if str(edge.get("labelpos", "r")).lower() != "c":
            if graph["rankdir"] in ("tb", "bt"):
                edge["width"] += edge["labeloffset"]
            else:
                edge["height"] += edge["labeloffset"]


def _inject_edge_label_proxies(g):
    for e in g.edges():
        edge = g.edge(e)
        if edge.get("width") and edge.get("height"):
            v = g.node(e["v"])
            w = g.node(e["w"])
            label = {"rank": (w["rank"] - v["rank"]) / 2 + v["rank"], "e": e}
            add_dummy_node(g, "edge-proxy", label, "_ep")


def _assign_rank_min_max(g):
    max_rank = 0
    for v in g.nodes():
        node = g.node(v)
        if node.get("borderTop"):
            node["minRank"] = g.node(node["borderTop"])["rank"]
            node["maxRank"] = g.node(node["borderBottom"])["rank"]
            max_rank = max(max_rank, node["maxRank"])
    g.graph()["maxRank"] = max_rank


def _remove_edge_label_proxies(g):
    for v in g.nodes():
        node = g.node(v)
        if node.get("dummy") == "edge-proxy":
            g.edge(node["e"])["labelRank"] = node["rank"]
            g.removeNode(v)


def _translate_graph(g):
    min_x = _INF
    max_x = 0
    min_y = _INF
    max_y = 0
    label = g.graph()
    margin_x = label.get("marginx", 0) or 0
    margin_y = label.get("marginy", 0) or 0

    def extremes(attrs):
        nonlocal min_x, max_x, min_y, max_y
        x, y = attrs["x"], attrs["y"]
        w = attrs.get("width", 0)
        h = attrs.get("height", 0)
        min_x = min(min_x, x - w / 2)
        max_x = max(max_x, x + w / 2)
        min_y = min(min_y, y - h / 2)
        max_y = max(max_y, y + h / 2)

    for v in g.nodes():
        extremes(g.node(v))
    for e in g.edges():
        edge = g.edge(e)
        if "x" in edge:
            extremes(edge)

    min_x -= margin_x
    min_y -= margin_y

    for v in g.nodes():
        node = g.node(v)
        node["x"] -= min_x
        node["y"] -= min_y

    for e in g.edges():
        edge = g.edge(e)
        for p in edge.get("points") or []:
            p["x"] -= min_x
            p["y"] -= min_y
        if "x" in edge:
            edge["x"] -= min_x
        if "y" in edge:
            edge["y"] -= min_y

    label["width"] = max_x - min_x + margin_x
    label["height"] = max_y - min_y + margin_y


def _assign_node_intersects(g):
    for e in g.edges():
        if e["v"] == e["w"]:
            continue
        edge = g.edge(e)
        node_v = g.node(e["v"])
        node_w = g.node(e["w"])
        if not edge.get("points"):
            edge["points"] = []
            p1 = node_w
            p2 = node_v
        else:
            p1 = edge["points"][0]
            p2 = edge["points"][-1]
        edge["points"].insert(0, intersect_rect(node_v, p1))
        edge["points"].append(intersect_rect(node_w, p2))


def _fixup_edge_label_coords(g):
    for e in g.edges():
        edge = g.edge(e)
        if "x" in edge:
            if edge.get("labelpos") in ("l", "r"):
                edge["width"] -= edge["labeloffset"]
            if edge.get("labelpos") == "l":
                edge["x"] -= edge["width"] / 2 + edge["labeloffset"]
            elif edge.get("labelpos") == "r":
                edge["x"] += edge["width"] / 2 + edge["labeloffset"]


def _reverse_points_for_reversed_edges(g):
    for e in g.edges():
        edge = g.edge(e)
        if edge.get("reversed"):
            edge["points"].reverse()


def _remove_border_nodes(g):
    for v in g.nodes():
        if g.children(v):
            node = g.node(v)
            t = g.node(node["borderTop"])
            b = g.node(node["borderBottom"])
            bl = node["borderLeft"]
            br = node["borderRight"]
            l = g.node(bl[max(bl)])
            r = g.node(br[max(br)])
            node["width"] = abs(r["x"] - l["x"])
            node["height"] = abs(b["y"] - t["y"])
            node["x"] = l["x"] + node["width"] / 2
            node["y"] = t["y"] + node["height"] / 2

    for v in g.nodes():
        if g.node(v).get("dummy") == "border":
            g.removeNode(v)


def _remove_self_edges(g):
    for e in g.edges():
        if e["v"] == e["w"]:
            node = g.node(e["v"])
            node.setdefault("selfEdges", []).append({"e": e, "label": g.edge(e)})
            g.removeEdge(e)


def _insert_self_edges(g):
    layers = build_layer_matrix(g)
    for layer in layers:
        order_shift = 0
        for i, v in enumerate(layer):
            node = g.node(v)
            if not isinstance(node.get("rank"), (int, float)):
                node["rank"] = 0
            node["order"] = i + order_shift
            for self_edge in node.get("selfEdges") or []:
                order_shift += 1
                add_dummy_node(
                    g, "selfedge",
                    {"width": self_edge["label"]["width"], "height": self_edge["label"]["height"],
                     "rank": node["rank"], "order": i + order_shift,
                     "e": self_edge["e"], "edgeLabel": self_edge["label"]},
                    "_se",
                )
            node.pop("selfEdges", None)


def _position_self_edges(g):
    for v in g.nodes():
        node = g.node(v)
        if node.get("dummy") == "selfedge":
            self_node = g.node(node["e"]["v"])
            x = self_node.get("x", 0) or 0
            y = self_node.get("y", 0) or 0
            w = self_node.get("width", 0) or 0
            h = self_node.get("height", 0) or 0
            node_x = node.get("x", x)
            node_y = node.get("y", y)
            dx = w / 2
            dy = h / 2
            label = node["edgeLabel"]
            label["points"] = [
                {"x": node_x + dx, "y": node_y - dy},
                {"x": node_x + dx, "y": node_y - dy},
                {"x": node_x, "y": node_y},
                {"x": node_x - dx, "y": node_y + dy},
                {"x": node_x - dx, "y": node_y + dy},
                {"x": node_x, "y": node_y},
                {"x": node_x, "y": node_y},
            ]
            label["x"] = node_x
            label["y"] = node_y
            g.setEdge(node["e"], label)
            g.removeNode(v)
