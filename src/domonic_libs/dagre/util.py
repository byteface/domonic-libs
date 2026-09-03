# Ported from dagrejs/dagre (MIT). Mirrors lib/util.ts.
"""Shared helpers for the dagre layout pipeline."""

from __future__ import annotations

import math

from .graphlib import Graph

_id_counter = [0]


def unique_id(prefix: str) -> str:
    _id_counter[0] += 1
    return prefix + str(_id_counter[0])


def add_dummy_node(graph: Graph, dummy_type: str, attrs: dict, name: str) -> str:
    v = name
    while graph.hasNode(v):
        v = unique_id(name)
    attrs["dummy"] = dummy_type
    graph.setNode(v, attrs)
    return v


def simplify(graph: Graph) -> Graph:
    simplified = Graph().setGraph(graph.graph())
    for v in graph.nodes():
        simplified.setNode(v, graph.node(v))
    for e in graph.edges():
        simple = simplified.edge(e["v"], e["w"]) or {"weight": 0, "minlen": 1}
        label = graph.edge(e)
        simplified.setEdge(
            e["v"], e["w"],
            {"weight": simple["weight"] + label["weight"],
             "minlen": max(simple["minlen"], label["minlen"])},
        )
    return simplified


def as_non_compound_graph(graph: Graph) -> Graph:
    simplified = Graph({"multigraph": graph.isMultigraph()}).setGraph(graph.graph())
    for v in graph.nodes():
        if not graph.children(v):
            simplified.setNode(v, graph.node(v))
    for e in graph.edges():
        simplified.setEdge(e, graph.edge(e))
    return simplified


def successor_weights(graph: Graph) -> dict:
    result = {}
    for v in graph.nodes():
        sucs: dict = {}
        for e in graph.outEdges(v) or []:
            sucs[e["w"]] = sucs.get(e["w"], 0) + graph.edge(e)["weight"]
        result[v] = sucs
    return result


def predecessor_weights(graph: Graph) -> dict:
    result = {}
    for v in graph.nodes():
        preds: dict = {}
        for e in graph.inEdges(v) or []:
            preds[e["v"]] = preds.get(e["v"], 0) + graph.edge(e)["weight"]
        result[v] = preds
    return result


def intersect_rect(rect: dict, point: dict) -> dict:
    x, y = rect["x"], rect["y"]
    dx = point["x"] - x
    dy = point["y"] - y
    w = rect["width"] / 2
    h = rect["height"] / 2
    if not dx and not dy:
        raise ValueError("Not possible to find intersection inside of the rectangle")
    if abs(dy) * w > abs(dx) * h:
        if dy < 0:
            h = -h
        sx = h * dx / dy
        sy = h
    else:
        if dx < 0:
            w = -w
        sx = w
        sy = w * dy / dx
    return {"x": x + sx, "y": y + sy}


def build_layer_matrix(graph: Graph):
    layering = [[] for _ in range(int(max_rank(graph)) + 1)]
    for v in graph.nodes():
        node = graph.node(v)
        rank = node.get("rank")
        if rank is not None:
            row = layering[int(rank)]
            order = node["order"]
            while len(row) <= order:
                row.append(None)
            row[order] = v
    return [[v for v in row if v is not None] for row in layering]


def normalize_ranks(graph: Graph) -> None:
    ranks = [
        graph.node(v).get("rank", math.inf) for v in graph.nodes()
    ]
    min_rank = min(ranks) if ranks else 0
    for v in graph.nodes():
        node = graph.node(v)
        if "rank" in node:
            node["rank"] -= min_rank


def remove_empty_ranks(graph: Graph) -> None:
    ranks = [graph.node(v)["rank"] for v in graph.nodes() if graph.node(v).get("rank") is not None]
    offset = min(ranks) if ranks else 0

    layers: dict[int, list] = {}
    for v in graph.nodes():
        rank = int(graph.node(v)["rank"] - offset)
        layers.setdefault(rank, []).append(v)

    delta = 0
    factor = graph.graph().get("nodeRankFactor", 1)
    max_layer = max(layers.keys()) if layers else -1
    for i in range(max_layer + 1):
        vs = layers.get(i)
        if vs is None and i % factor != 0:
            delta -= 1
        elif vs is not None and delta:
            for v in vs:
                graph.node(v)["rank"] += delta


def add_border_node(graph: Graph, prefix: str, rank=None, order=None) -> str:
    node = {"width": 0, "height": 0}
    if rank is not None or order is not None:
        node["rank"] = rank
        node["order"] = order
    return add_dummy_node(graph, "border", node, prefix)


def max_rank(graph: Graph) -> int:
    ranks = [graph.node(v).get("rank") for v in graph.nodes()]
    ranks = [r for r in ranks if r is not None]
    return max(ranks) if ranks else 0


def partition(collection, fn):
    lhs, rhs = [], []
    for value in collection:
        (lhs if fn(value) else rhs).append(value)
    return {"lhs": lhs, "rhs": rhs}


def dagre_range(start, limit=None, step=1):
    if limit is None:
        start, limit = 0, start
    out = []
    i = start
    if step >= 0:
        while i < limit:
            out.append(i)
            i += step
    else:
        while limit < i:
            out.append(i)
            i += step
    return out


def pick(source: dict, keys) -> dict:
    return {k: source[k] for k in keys if source.get(k) is not None}


def map_values(obj: dict, func_or_prop):
    if isinstance(func_or_prop, str):
        prop = func_or_prop
        func = lambda val, key: val[prop]
    else:
        func = func_or_prop
    return {k: func(v, k) for k, v in obj.items()}


def zip_object(props, values):
    return {key: values[i] for i, key in enumerate(props)}
