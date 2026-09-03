# Ported from dagrejs/dagre (MIT). Mirrors lib/greedy-fas.ts.
"""Eades-Lin-Smyth greedy heuristic for a feedback arc set (weighted)."""

from __future__ import annotations

from .graphlib import Graph
from .list import List


class _Entry:
    __slots__ = ("_next", "_prev", "v", "in_", "out")

    def __init__(self, v):
        self._next = None
        self._prev = None
        self.v = v
        self.in_ = 0
        self.out = 0


def _default_weight(_e):
    return 1


def greedy_fas(graph: Graph, weight_fn=None):
    if graph.nodeCount() <= 1:
        return []
    weight_fn = weight_fn or _default_weight
    fas_graph, buckets, zero_idx = _build_state(graph, weight_fn)
    results = _do_greedy_fas(fas_graph, buckets, zero_idx)
    out = []
    for edge in results:
        out.extend(graph.outEdges(edge["v"], edge["w"]) or [])
    return out


def _do_greedy_fas(g, buckets, zero_idx):
    results = []
    sources = buckets[-1]
    sinks = buckets[0]

    while g.nodeCount():
        entry = sinks.dequeue()
        while entry:
            _remove_node(g, buckets, zero_idx, entry)
            entry = sinks.dequeue()
        entry = sources.dequeue()
        while entry:
            _remove_node(g, buckets, zero_idx, entry)
            entry = sources.dequeue()
        if g.nodeCount():
            for i in range(len(buckets) - 2, 0, -1):
                entry = buckets[i].dequeue()
                if entry:
                    results += _remove_node(g, buckets, zero_idx, entry, True) or []
                    break
    return results


def _remove_node(graph, buckets, zero_idx, entry, collect_predecessors=False):
    collected = [] if collect_predecessors else None

    for edge in graph.inEdges(entry.v) or []:
        weight = graph.edge(edge)
        u_entry = graph.node(edge["v"])
        if collect_predecessors:
            collected.append({"v": edge["v"], "w": edge["w"]})
        u_entry.out -= weight
        _assign_bucket(buckets, zero_idx, u_entry)

    for edge in graph.outEdges(entry.v) or []:
        weight = graph.edge(edge)
        w_entry = graph.node(edge["w"])
        w_entry.in_ -= weight
        _assign_bucket(buckets, zero_idx, w_entry)

    graph.removeNode(entry.v)
    return collected


def _build_state(graph, weight_fn):
    fas_graph = Graph()
    max_in = 0
    max_out = 0

    for v in graph.nodes():
        fas_graph.setNode(v, _Entry(v))

    for edge in graph.edges():
        prev_weight = fas_graph.edge(edge["v"], edge["w"]) or 0
        weight = weight_fn(edge)
        fas_graph.setEdge(edge["v"], edge["w"], prev_weight + weight)
        v_node = fas_graph.node(edge["v"])
        w_node = fas_graph.node(edge["w"])
        v_node.out += weight
        w_node.in_ += weight
        max_out = max(max_out, v_node.out)
        max_in = max(max_in, w_node.in_)

    buckets = [List() for _ in range(max_out + max_in + 3)]
    zero_idx = max_in + 1
    for v in fas_graph.nodes():
        _assign_bucket(buckets, zero_idx, fas_graph.node(v))
    return fas_graph, buckets, zero_idx


def _assign_bucket(buckets, zero_idx, entry):
    if not entry.out:
        buckets[0].enqueue(entry)
    elif not entry.in_:
        buckets[-1].enqueue(entry)
    else:
        buckets[entry.out - entry.in_ + zero_idx].enqueue(entry)
