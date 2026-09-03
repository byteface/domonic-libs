# Ported from dagrejs/dagre (MIT). Mirrors lib/acyclic.ts.
"""Make the graph acyclic by reversing a feedback arc set; ``undo`` restores it."""

from __future__ import annotations

from .greedy_fas import greedy_fas
from .util import unique_id


def run(graph, old_graph=None):
    if graph.graph().get("acyclicer") == "greedy":
        fas = greedy_fas(graph, lambda e: graph.edge(e)["weight"])
    else:
        fas = _dfs_fas(graph, old_graph)
    for e in fas:
        label = graph.edge(e)
        graph.removeEdge(e)
        label["forwardName"] = e.get("name")
        label["reversed"] = True
        graph.setEdge(e["w"], e["v"], label, unique_id("rev"))


def _dfs_fas(graph, old_graph):
    fas = []
    stack: dict = {}
    visited: dict = {}

    def dfs(v):
        if v in visited:
            return
        visited[v] = True
        stack[v] = True
        for e in graph.outEdges(v) or []:
            if e["w"] in stack:
                fas.append(e)
            else:
                dfs(e["w"])
        del stack[v]

    for v in graph.sources():
        dfs(v)
    for v in graph.nodes():
        dfs(v)
    return fas


def undo(graph):
    for e in graph.edges():
        label = graph.edge(e)
        if label.get("reversed"):
            graph.removeEdge(e)
            forward_name = label.get("forwardName")
            label.pop("reversed", None)
            label.pop("forwardName", None)
            graph.setEdge(e["w"], e["v"], label, forward_name)
