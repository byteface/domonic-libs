# Ported from dagrejs/dagre (MIT). Mirrors lib/add-border-segments.ts.
"""Add left/right border dummy chains along each compound node's rank span."""

from __future__ import annotations

from .graphlib import GRAPH_NODE
from .util import add_dummy_node


def add_border_segments(graph):
    def dfs(v):
        children = graph.children(v)
        node = graph.node(v)
        for c in children:
            dfs(c)
        if node and "minRank" in node:
            node["borderLeft"] = {}
            node["borderRight"] = {}
            rank = node["minRank"]
            while rank < node["maxRank"] + 1:
                _add_border_node(graph, "borderLeft", "_bl", v, node, rank)
                _add_border_node(graph, "borderRight", "_br", v, node, rank)
                rank += 1

    for v in graph.children(GRAPH_NODE):
        dfs(v)


def _add_border_node(graph, prop, prefix, sg, sg_node, rank):
    label = {"width": 0, "height": 0, "rank": rank, "borderType": prop}
    prev = sg_node[prop].get(rank - 1)
    curr = add_dummy_node(graph, "border", label, prefix)
    sg_node[prop][rank] = curr
    graph.setParent(curr, sg)
    if prev:
        graph.setEdge(prev, curr, {"weight": 1})
