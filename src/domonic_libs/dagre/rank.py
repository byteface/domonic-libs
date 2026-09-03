# Ported from dagrejs/dagre (MIT). Combines lib/rank/{index,util,feasible-tree,
# network-simplex}.ts -- they are tightly coupled.
"""Assign a ``rank`` to every node, honouring edge ``minlen``.

``rank()`` dispatches on ``graph.graph()["ranker"]`` (default: network simplex,
the Gansner et al. technique). Longest-path gives the initial ranking; the tight
tree removes slack; network simplex then iteratively exchanges tree edges with
negative cut values.
"""

from __future__ import annotations

import math

from .graphlib import Graph, postorder, preorder
from .util import simplify

_INF = math.inf


def rank(graph):
    ranker = graph.graph().get("ranker")
    if callable(ranker):
        ranker(graph)
    elif ranker == "tight-tree":
        longest_path(graph)
        feasible_tree(graph)
    elif ranker == "longest-path":
        longest_path(graph)
    elif ranker == "none":
        pass
    else:
        network_simplex(graph)


# -- longest path / slack ------------------------------------------


def longest_path(graph):
    visited: dict = {}

    def dfs(v):
        label = graph.node(v)
        if v in visited:
            return label["rank"]
        visited[v] = True
        mins = []
        for e in graph.outEdges(v) or []:
            mins.append(dfs(e["w"]) - graph.edge(e)["minlen"])
        r = min(mins) if mins else _INF
        if r == _INF:
            r = 0
        label["rank"] = r
        return r

    for v in graph.sources():
        dfs(v)


def slack(graph, edge):
    return graph.node(edge["w"])["rank"] - graph.node(edge["v"])["rank"] - graph.edge(edge)["minlen"]


# -- feasible (tight) tree ----------------------------------------


def feasible_tree(graph):
    tree = Graph({"directed": False})
    nodes = graph.nodes()
    if not nodes:
        raise ValueError("Graph must have at least one node")
    start = nodes[0]
    size = graph.nodeCount()
    tree.setNode(start, {})

    while _tight_tree(tree, graph) < size:
        edge = _find_min_slack_edge(tree, graph)
        if not edge:
            break
        delta = slack(graph, edge) if tree.hasNode(edge["v"]) else -slack(graph, edge)
        for v in tree.nodes():
            graph.node(v)["rank"] += delta
    return tree


def _tight_tree(tree, graph):
    def dfs(v):
        for e in graph.nodeEdges(v) or []:
            w = e["w"] if v == e["v"] else e["v"]
            if not tree.hasNode(w) and not slack(graph, e):
                tree.setNode(w, {})
                tree.setEdge(v, w, {})
                dfs(w)

    for v in tree.nodes():
        dfs(v)
    return tree.nodeCount()


def _find_min_slack_edge(tree, graph):
    best_slack = _INF
    best = None
    for edge in graph.edges():
        if tree.hasNode(edge["v"]) != tree.hasNode(edge["w"]):
            s = slack(graph, edge)
            if s < best_slack:
                best_slack, best = s, edge
    return best


# -- network simplex --------------------------------------------


def network_simplex(graph):
    graph = simplify(graph)
    longest_path(graph)
    t = feasible_tree(graph)
    _init_low_lim_values(t)
    _init_cut_values(t, graph)

    e = _leave_edge(t)
    while e:
        f = _enter_edge(t, graph, e)
        _exchange_edges(t, graph, e, f)
        e = _leave_edge(t)

    # simplify() worked on a copy -- push ranks back to the caller's nodes is
    # unnecessary because `graph` here IS the simplified copy and callers read
    # ranks from the object they passed... but dagre relies on longest_path/
    # feasible_tree mutating shared label objects. simplify() copies labels by
    # reference, so rank writes land on the originals.


def _init_cut_values(tree, graph):
    visited = postorder(tree, tree.nodes())
    visited = visited[:-1]
    for v in visited:
        _assign_cut_value(tree, graph, v)


def _assign_cut_value(tree, graph, child):
    parent = tree.node(child)["parent"]
    tree.edge(child, parent)["cutvalue"] = _calc_cut_value(tree, graph, child)


def _calc_cut_value(tree, graph, child):
    parent = tree.node(child)["parent"]
    child_is_tail = True
    graph_edge = graph.edge(child, parent)
    if not graph_edge:
        child_is_tail = False
        graph_edge = graph.edge(parent, child)

    cut_value = graph_edge["weight"]

    for edge in graph.nodeEdges(child) or []:
        is_out_edge = edge["v"] == child
        other = edge["w"] if is_out_edge else edge["v"]
        if other != parent:
            points_to_head = is_out_edge == child_is_tail
            other_weight = graph.edge(edge)["weight"]
            cut_value += other_weight if points_to_head else -other_weight
            if tree.hasEdge(child, other):
                other_cut = tree.edge(child, other)["cutvalue"]
                cut_value += -other_cut if points_to_head else other_cut
    return cut_value


def _init_low_lim_values(tree, root=None):
    if root is None:
        root = tree.nodes()[0]
    _dfs_assign_low_lim(tree, {}, 1, root, None)


def _dfs_assign_low_lim(tree, visited, next_lim, v, parent):
    low = next_lim
    label = tree.node(v)
    visited[v] = True
    for w in tree.neighbors(v) or []:
        if w not in visited:
            next_lim = _dfs_assign_low_lim(tree, visited, next_lim, w, v)
    label["low"] = low
    label["lim"] = next_lim
    next_lim += 1
    if parent:
        label["parent"] = parent
    else:
        label.pop("parent", None)
    return next_lim


def _leave_edge(tree):
    for e in tree.edges():
        if tree.edge(e)["cutvalue"] < 0:
            return e
    return None


def _enter_edge(tree, graph, edge):
    v, w = edge["v"], edge["w"]
    if not graph.hasEdge(v, w):
        v, w = edge["w"], edge["v"]

    v_label = tree.node(v)
    w_label = tree.node(w)
    tail_label = v_label
    flip = False
    if v_label["lim"] > w_label["lim"]:
        tail_label = w_label
        flip = True

    candidates = [
        e for e in graph.edges()
        if flip == _is_descendant(tree.node(e["v"]), tail_label)
        and flip != _is_descendant(tree.node(e["w"]), tail_label)
    ]

    best = candidates[0]
    for e in candidates[1:]:
        if slack(graph, e) < slack(graph, best):
            best = e
    return best


def _exchange_edges(t, g, e, f):
    t.removeEdge(e["v"], e["w"])
    t.setEdge(f["v"], f["w"], {})
    _init_low_lim_values(t)
    _init_cut_values(t, g)
    _update_ranks(t, g)


def _update_ranks(t, g):
    root = next((v for v in t.nodes() if not t.node(v).get("parent")), None)
    if not root:
        return
    vs = preorder(t, [root])[1:]
    for v in vs:
        parent = t.node(v)["parent"]
        edge = g.edge(v, parent)
        flipped = False
        if not edge:
            edge = g.edge(parent, v)
            flipped = True
        g.node(v)["rank"] = g.node(parent)["rank"] + (
            edge["minlen"] if flipped else -edge["minlen"]
        )


def _is_descendant(v_label, root_label):
    return root_label["low"] <= v_label["lim"] <= root_label["lim"]
