# Ported from dagrejs/dagre (MIT). Mirrors lib/normalize.ts.
"""Split long edges into 1-rank segments with dummy nodes; ``undo`` collapses them."""

from __future__ import annotations

from .util import add_dummy_node


def run(graph):
    graph.graph()["dummyChains"] = []
    for edge in graph.edges():
        _normalize_edge(graph, edge)


def _normalize_edge(graph, e):
    v = e["v"]
    v_rank = graph.node(v)["rank"]
    w = e["w"]
    w_rank = graph.node(w)["rank"]
    name = e.get("name")
    edge_label = graph.edge(e)
    label_rank = edge_label.get("labelRank")

    if w_rank == v_rank + 1:
        return

    graph.removeEdge(e)

    i = 0
    v_rank += 1
    while v_rank < w_rank:
        edge_label["points"] = []
        attrs = {
            "width": 0,
            "height": 0,
            "edgeLabel": edge_label,
            "edgeObj": e,
            "rank": v_rank,
        }
        dummy = add_dummy_node(graph, "edge", attrs, "_d")
        if v_rank == label_rank:
            attrs["width"] = edge_label["width"]
            attrs["height"] = edge_label["height"]
            attrs["dummy"] = "edge-label"
            attrs["labelpos"] = edge_label["labelpos"]
        graph.setEdge(v, dummy, {"weight": edge_label["weight"]}, name)
        if i == 0:
            graph.graph()["dummyChains"].append(dummy)
        v = dummy
        i += 1
        v_rank += 1

    graph.setEdge(v, w, {"weight": edge_label["weight"]}, name)


def undo(graph):
    for start in graph.graph()["dummyChains"]:
        v = start
        node = graph.node(v)
        orig_label = node["edgeLabel"]
        graph.setEdge(node["edgeObj"], orig_label)
        while node.get("dummy"):
            w = graph.successors(v)[0]
            graph.removeNode(v)
            orig_label["points"].append({"x": node["x"], "y": node["y"]})
            if node["dummy"] == "edge-label":
                orig_label["x"] = node["x"]
                orig_label["y"] = node["y"]
                orig_label["width"] = node["width"]
                orig_label["height"] = node["height"]
            v = w
            node = graph.node(v)
