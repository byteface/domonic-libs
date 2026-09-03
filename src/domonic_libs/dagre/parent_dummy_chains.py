# Ported from dagrejs/dagre (MIT). Mirrors lib/parent-dummy-chains.ts.
"""Re-parent each dummy chain so it enters/leaves compound clusters correctly."""

from __future__ import annotations

from .graphlib import GRAPH_NODE


def parent_dummy_chains(graph):
    postorder_nums = _postorder(graph)
    dummy_chains = graph.graph().get("dummyChains")
    if not isinstance(dummy_chains, list):
        return
    for start in dummy_chains:
        v = start
        node = graph.node(v)
        edge_obj = node["edgeObj"]
        path_data = _find_path(graph, postorder_nums, edge_obj["v"], edge_obj["w"])
        path = path_data["path"]
        lca = path_data["lca"]
        path_idx = 0
        ascending = True

        while v != edge_obj["w"]:
            node = graph.node(v)
            if ascending:
                while (
                    path_idx < len(path)
                    and path[path_idx] != lca
                    and graph.node(path[path_idx])["maxRank"] < node["rank"]
                ):
                    path_idx += 1
                if path_idx < len(path) and path[path_idx] == lca:
                    ascending = False
            if not ascending:
                while (
                    path_idx < len(path) - 1
                    and graph.node(path[path_idx + 1])["minRank"] <= node["rank"]
                ):
                    path_idx += 1
            path_v = path[path_idx] if path_idx < len(path) else None
            if path_v is not None:
                graph.setParent(v, path_v)
            v = graph.successors(v)[0]


def _find_path(graph, postorder_nums, v, w):
    v_path = []
    w_path = []
    low = min(postorder_nums[v]["low"], postorder_nums[w]["low"])
    lim = max(postorder_nums[v]["lim"], postorder_nums[w]["lim"])

    parent = v
    while True:
        parent = graph.parent(parent)
        v_path.append(parent)
        if not (
            parent
            and (postorder_nums[parent]["low"] > low or lim > postorder_nums[parent]["lim"])
        ):
            break
    lca = parent

    w_parent = w
    w_parent = graph.parent(w_parent)
    while w_parent != lca:
        w_path.append(w_parent)
        w_parent = graph.parent(w_parent)

    return {"path": v_path + list(reversed(w_path)), "lca": lca}


def _postorder(graph):
    result: dict = {}
    lim = [0]

    def dfs(v):
        low = lim[0]
        for c in graph.children(v):
            dfs(c)
        result[v] = {"low": low, "lim": lim[0]}
        lim[0] += 1

    for v in graph.children(GRAPH_NODE):
        dfs(v)
    return result
