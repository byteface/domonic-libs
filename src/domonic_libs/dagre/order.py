# Ported from dagrejs/dagre (MIT). Combines lib/order/*.ts.
"""Crossing minimisation -- assign an ``order`` within each rank.

Median/barycenter heuristic (Gansner et al. / Barth et al. cross counting) with
the Forster constrained two-level reduction for compound graphs. ``old_nodes``
(incremental relayout) is not supported, so the ``compareByOldOrder`` tie-break
degrades to insertion order -- fine for a from-scratch layout.
"""

from __future__ import annotations

import math
from functools import cmp_to_key

from .graphlib import Graph
from .util import build_layer_matrix, dagre_range, max_rank, pick, unique_id, zip_object

_INF = math.inf


def order(graph, opts=None):
    opts = opts or {}
    mr = max_rank(graph)
    down = _build_layer_graphs(graph, dagre_range(1, mr + 1), "inEdges")
    up = _build_layer_graphs(graph, dagre_range(mr - 1, -1, -1), "outEdges")

    layering = _init_order(graph)
    _assign_order(graph, layering)

    if opts.get("disableOptimalOrderHeuristic"):
        return

    best_cc = _INF
    best = None
    i = 0
    last_best = 0
    while last_best < 4:
        _sweep_layer_graphs(down if i % 2 else up, i % 4 >= 2)
        layering = build_layer_matrix(graph)
        cc = cross_count(graph, layering)
        if cc < best_cc:
            last_best = 0
            best = [list(row) for row in layering]
            best_cc = cc
        else:
            if cc == best_cc:
                best = [list(row) for row in layering]
            last_best += 1
        i += 1

    _assign_order(graph, best)


def _assign_order(graph, layering):
    for layer in layering:
        for i, v in enumerate(layer):
            graph.node(v)["order"] = i


def _build_layer_graphs(graph, ranks, relationship):
    nodes_by_rank: dict = {}
    for v in graph.nodes():
        node = graph.node(v)
        if isinstance(node.get("rank"), (int, float)):
            nodes_by_rank.setdefault(node["rank"], []).append(v)
        if isinstance(node.get("minRank"), (int, float)) and isinstance(node.get("maxRank"), (int, float)):
            for r in range(node["minRank"], node["maxRank"] + 1):
                if r != node.get("rank"):
                    nodes_by_rank.setdefault(r, []).append(v)
    return [_build_layer_graph(graph, r, relationship, nodes_by_rank.get(r, [])) for r in ranks]


def _build_layer_graph(graph, rank, relationship, nodes_with_rank):
    root = unique_id("_root")
    while graph.hasNode(root):
        root = unique_id("_root")
    result = Graph({"compound": True}).setGraph({"root": root})
    result.setDefaultNodeLabel(lambda v: graph.node(v))

    for v in nodes_with_rank:
        node = graph.node(v)
        parent = graph.parent(v)
        if node.get("rank") == rank or (
            node.get("minRank") is not None and node["minRank"] <= rank <= node["maxRank"]
        ):
            result.setNode(v)
            result.setParent(v, parent or root)
            edges = (graph.inEdges(v) if relationship == "inEdges" else graph.outEdges(v)) or []
            for e in edges:
                u = e["w"] if e["v"] == v else e["v"]
                existing = result.edge(u, v)
                weight = existing["weight"] if existing is not None else 0
                result.setEdge(u, v, {"weight": graph.edge(e)["weight"] + weight})
            if "minRank" in node:
                result.setNode(v, {
                    "borderLeft": node["borderLeft"][rank],
                    "borderRight": node["borderRight"][rank],
                })
    return result


def _sweep_layer_graphs(layer_graphs, switch_bias):
    bias_right = [True]
    cg = Graph()
    for lg in layer_graphs:
        root = lg.graph()["root"]
        sorted_result, used_bias = _sort_subgraph(lg, root, cg, None, bias_right[0])
        if switch_bias and used_bias:
            bias_right[0] = not bias_right[0]
        for i, v in enumerate(sorted_result["vs"]):
            lg.node(v)["order"] = i
        _add_subgraph_constraints(lg, cg, sorted_result["vs"])


# -- init order --------------------------------------------------


def _init_order(graph):
    visited: dict = {}
    simple_nodes = [v for v in graph.nodes() if not graph.children(v)]
    ranks = [int(graph.node(v)["rank"]) for v in simple_nodes]
    mr = max(ranks) if ranks else 0
    layers = [[] for _ in range(mr + 1)]

    def dfs(v):
        if visited.get(v):
            return
        visited[v] = True
        node = graph.node(v)
        layers[int(node["rank"])].append(v)
        for w in graph.successors(v) or []:
            dfs(w)

    for v in sorted(simple_nodes, key=lambda a: graph.node(a)["rank"]):
        dfs(v)
    return layers


# -- barycenter -------------------------------------------------


def _barycenter(graph, movable):
    out = []
    for v in movable:
        in_v = graph.inEdges(v)
        if not in_v:
            out.append({"v": v})
            continue
        s = 0.0
        w = 0.0
        for e in in_v:
            edge = graph.edge(e)
            node_u = graph.node(e["v"])
            s += edge["weight"] * node_u["order"]
            w += edge["weight"]
        out.append({"v": v, "barycenter": s / w, "weight": w})
    return out


# -- resolve conflicts ----------------------------------------


def _resolve_conflicts(entries, constraint_graph):
    mapped: dict = {}
    for i, entry in enumerate(entries):
        tmp = {"indegree": 0, "in": [], "out": [], "vs": [entry["v"]], "i": i, "merged": False}
        if entry.get("barycenter") is not None:
            tmp["barycenter"] = entry["barycenter"]
            tmp["weight"] = entry["weight"]
        mapped[entry["v"]] = tmp

    for e in constraint_graph.edges():
        ev = mapped.get(e["v"])
        ew = mapped.get(e["w"])
        if ev is not None and ew is not None:
            ew["indegree"] += 1
            ev["out"].append(ew)

    source_set = [e for e in mapped.values() if not e["indegree"]]
    return _do_resolve_conflicts(source_set)


def _do_resolve_conflicts(source_set):
    entries = []

    def merge_entries(target, source):
        s = 0.0
        w = 0.0
        if target.get("weight"):
            s += target["barycenter"] * target["weight"]
            w += target["weight"]
        if source.get("weight"):
            s += source["barycenter"] * source["weight"]
            w += source["weight"]
        target["vs"] = source["vs"] + target["vs"]
        target["barycenter"] = s / w
        target["weight"] = w
        target["i"] = min(source["i"], target["i"])
        source["merged"] = True

    while source_set:
        entry = source_set.pop()
        entries.append(entry)
        for u_entry in reversed(entry["in"]):
            if u_entry.get("merged"):
                continue
            if (
                u_entry.get("barycenter") is None
                or entry.get("barycenter") is None
                or u_entry["barycenter"] >= entry["barycenter"]
            ):
                merge_entries(entry, u_entry)
        for w_entry in entry["out"]:
            w_entry["in"].append(entry)
            w_entry["indegree"] -= 1
            if w_entry["indegree"] == 0:
                source_set.append(w_entry)

    return [pick(e, ["vs", "i", "barycenter", "weight"]) for e in entries if not e.get("merged")]


# -- sort -----------------------------------------------------


def _sort(entries, reversed_pairs=None, bias_right=False):
    reversed_pairs = reversed_pairs or {}
    if isinstance(reversed_pairs, bool):
        bias_right = reversed_pairs
        reversed_pairs = {}

    sortable = [e for e in entries if "barycenter" in e]
    unsortable = sorted((e for e in entries if "barycenter" not in e), key=lambda e: -e["i"])

    def cmp(a, b):
        if a["barycenter"] < b["barycenter"]:
            return -1
        if a["barycenter"] > b["barycenter"]:
            return 1
        return (b["i"] - a["i"]) if bias_right else (a["i"] - b["i"])

    sortable.sort(key=cmp_to_key(cmp))

    for key, value in reversed_pairs.items():
        for idx, entry in enumerate(sortable):
            if entry["vs"] and entry["vs"][0] == key:
                sortable.insert(idx + 1, value)
                break

    vs: list = []

    def consume_unsortable(index):
        while unsortable and unsortable[-1]["i"] <= index:
            last = unsortable.pop()
            vs.append(last["vs"])
            index += 1
        return index

    s = 0.0
    w = 0.0
    vs_index = consume_unsortable(0)
    for entry in sortable:
        vs_index += len(entry["vs"])
        vs.append(entry["vs"])
        s += entry["barycenter"] * entry["weight"]
        w += entry["weight"]
        vs_index = consume_unsortable(vs_index)

    flat = [v for group in vs for v in group]
    result = {"vs": flat}
    if w:
        result["barycenter"] = s / w
        result["weight"] = w
    return result


# -- sort subgraph -----------------------------------------


def _sort_subgraph(graph, v, constraint_graph, old_nodes=None, bias_right=None):
    movable = graph.children(v)
    node = graph.node(v)
    bl = node.get("borderLeft") if node else None
    br = node.get("borderRight") if node else None
    subgraphs: dict = {}

    if bl:
        movable = [w for w in movable if w != bl and w != br]

    barycenters = _barycenter(graph, movable)
    for entry in barycenters:
        if graph.children(entry["v"]):
            sub_result, _ = _sort_subgraph(graph, entry["v"], constraint_graph, old_nodes, bias_right)
            subgraphs[entry["v"]] = sub_result
            if "barycenter" in sub_result:
                _merge_barycenters(entry, sub_result)

    entries = _resolve_conflicts(barycenters, constraint_graph)
    _expand_subgraphs(entries, subgraphs)

    reversed_pairs: dict = {}
    used_bias = False
    i = 0
    while i < len(entries):
        j = i + 1
        while j < len(entries):
            ei, ej = entries[i], entries[j]
            if not ei or not ej or not ei.get("barycenter") or not ej.get("barycenter"):
                j += 1
                continue
            if ei["barycenter"] == ej["barycenter"]:
                name_i = ei["vs"][0] if ei["vs"] else ""
                name_j = ej["vs"][0] if ej["vs"] else ""
                node_i = graph.node(name_i)
                node_j = graph.node(name_j)
                if (
                    node_i and node_j
                    and node_i.get("dummy") == "edge" and node_j.get("dummy") == "edge"
                    and node_i.get("edgeObj", {}).get("v") == node_j.get("edgeObj", {}).get("v")
                    and node_i.get("edgeObj", {}).get("w") == node_j.get("edgeObj", {}).get("w")
                ):
                    if node_i["edgeLabel"].get("reversed"):
                        reversed_pairs[name_j] = entries[i]
                        entries.pop(i)
                        i -= 1
                        break
                    reversed_pairs[name_i] = entries[j]
                    entries.pop(j)
                    j -= 1
                else:
                    used_bias = True
            j += 1
        i += 1

    result = _sort(entries, reversed_pairs, bool(bias_right))

    if bl and br:
        result["vs"] = [bl] + result["vs"] + [br]
        bl_preds = graph.predecessors(bl)
        if bl_preds:
            bl_pred = graph.node(bl_preds[0])
            br_pred = graph.node(graph.predecessors(br)[0])
            if "barycenter" not in result:
                result["barycenter"] = 0
                result["weight"] = 0
            result["barycenter"] = (
                result["barycenter"] * result["weight"] + bl_pred["order"] + br_pred["order"]
            ) / (result["weight"] + 2)
            result["weight"] += 2

    return result, used_bias


def _expand_subgraphs(entries, subgraphs):
    for entry in entries:
        new_vs = []
        for v in entry["vs"]:
            if v in subgraphs:
                new_vs.extend(subgraphs[v]["vs"])
            else:
                new_vs.append(v)
        entry["vs"] = new_vs


def _merge_barycenters(target, other):
    if target.get("barycenter") is not None:
        target["barycenter"] = (
            target["barycenter"] * target["weight"] + other["barycenter"] * other["weight"]
        ) / (target["weight"] + other["weight"])
        target["weight"] += other["weight"]
    else:
        target["barycenter"] = other["barycenter"]
        target["weight"] = other["weight"]


# -- subgraph constraints ------------------------------------


def _add_subgraph_constraints(graph, constraint_graph, vs):
    prev: dict = {}
    root_prev = [None]

    for v in vs:
        child = graph.parent(v)
        while child:
            parent = graph.parent(child)
            if parent:
                prev_child = prev.get(parent)
                prev[parent] = child
            else:
                prev_child = root_prev[0]
                root_prev[0] = child
            if prev_child and prev_child != child:
                constraint_graph.setEdge(prev_child, child)
                break
            child = parent


# -- cross count -------------------------------------------


def cross_count(graph, layering):
    cc = 0
    for i in range(1, len(layering)):
        cc += _two_layer_cross_count(graph, layering[i - 1], layering[i])
    return cc


def _two_layer_cross_count(graph, north_layer, south_layer):
    south_pos = zip_object(south_layer, list(range(len(south_layer))))
    south_entries = []
    for v in north_layer:
        edges = graph.outEdges(v)
        if not edges:
            continue
        chunk = sorted(
            ({"pos": south_pos[e["w"]], "weight": graph.edge(e)["weight"]} for e in edges),
            key=lambda x: x["pos"],
        )
        south_entries.extend(chunk)

    first_index = 1
    while first_index < len(south_layer):
        first_index <<= 1
    tree_size = 2 * first_index - 1
    first_index -= 1
    tree = [0] * tree_size

    cc = 0
    for entry in south_entries:
        index = entry["pos"] + first_index
        tree[index] += entry["weight"]
        weight_sum = 0
        while index > 0:
            if index % 2:
                weight_sum += tree[index + 1]
            index = (index - 1) >> 1
            tree[index] += entry["weight"]
        cc += entry["weight"] * weight_sum
    return cc
