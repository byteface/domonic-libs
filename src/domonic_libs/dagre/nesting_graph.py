# Ported from dagrejs/dagre (MIT). Mirrors lib/nesting-graph.ts.
"""Sander's nesting graph -- dummy tops/bottoms for subgraphs, minlen scaling so
nodes and border nodes never share a rank, and a root to keep it connected."""

from __future__ import annotations

from .graphlib import GRAPH_NODE
from .util import add_border_node, add_dummy_node


def run(graph):
    root = add_dummy_node(graph, "root", {}, "_root")
    depths = _tree_depths(graph)
    height = (max(depths.values()) if depths else 1) - 1
    node_sep = 2 * height + 1

    graph.graph()["nestingRoot"] = root

    for e in graph.edges():
        graph.edge(e)["minlen"] *= node_sep

    weight = _sum_weights(graph) + 1

    for child in graph.children(GRAPH_NODE):
        _dfs(graph, root, node_sep, weight, height, depths, child)

    graph.graph()["nodeRankFactor"] = node_sep


def _dfs(graph, root, node_sep, weight, height, depths, v):
    children = graph.children(v)
    if not children:
        if v != root:
            graph.setEdge(root, v, {"weight": 0, "minlen": node_sep})
        return

    top = add_border_node(graph, "_bt")
    bottom = add_border_node(graph, "_bb")
    label = graph.node(v)

    graph.setParent(top, v)
    label["borderTop"] = top
    graph.setParent(bottom, v)
    label["borderBottom"] = bottom

    for child in children:
        _dfs(graph, root, node_sep, weight, height, depths, child)
        child_node = graph.node(child)
        child_top = child_node["borderTop"] if child_node.get("borderTop") else child
        child_bottom = child_node["borderBottom"] if child_node.get("borderBottom") else child
        this_weight = weight if child_node.get("borderTop") else 2 * weight
        minlen = 1 if child_top != child_bottom else height - depths.get(v, 0) + 1

        graph.setEdge(top, child_top, {"weight": this_weight, "minlen": minlen, "nestingEdge": True})
        graph.setEdge(child_bottom, bottom, {"weight": this_weight, "minlen": minlen, "nestingEdge": True})

    if not graph.parent(v):
        graph.setEdge(root, top, {"weight": 0, "minlen": height + depths.get(v, 0)})


def _tree_depths(graph):
    depths: dict = {}

    def dfs(v, depth):
        for child in graph.children(v):
            dfs(child, depth + 1)
        depths[v] = depth

    for v in graph.children(GRAPH_NODE):
        dfs(v, 1)
    return depths


def _sum_weights(graph):
    return sum(graph.edge(e)["weight"] for e in graph.edges())


def cleanup(graph):
    label = graph.graph()
    graph.removeNode(label["nestingRoot"])
    label.pop("nestingRoot", None)
    for e in graph.edges():
        if graph.edge(e).get("nestingEdge"):
            graph.removeEdge(e)
