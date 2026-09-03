# Ported from dagrejs/dagre (MIT). Combines lib/position/{index,bk}.ts.
"""Coordinate assignment.

``position()`` sets ``y`` per rank (``positionY``) and ``x`` via Brandes-Köpf
"Fast and Simple Horizontal Coordinate Assignment" (``positionX``): four extreme
alignments (up/down x left/right), each compacted, then balanced to the median.
The ``corePath`` optimisation is not ported.
"""

from __future__ import annotations

import math

from .graphlib import Graph
from .util import as_non_compound_graph, build_layer_matrix, map_values

_INF = math.inf
_NINF = -math.inf


def position(graph, core_path=None):
    graph = as_non_compound_graph(graph)
    _position_y(graph)
    for v, x in position_x(graph).items():
        graph.node(v)["x"] = x


def _position_y(graph):
    layering = build_layer_matrix(graph)
    label = graph.graph()
    rank_sep = label["ranksep"]
    rank_align = label.get("rankalign")
    prev_y = 0
    for layer in layering:
        max_height = 0
        for v in layer:
            h = graph.node(v).get("height", 0) or 0
            if h > max_height:
                max_height = h
        for v in layer:
            node = graph.node(v)
            if rank_align == "top":
                node["y"] = prev_y + node["height"] / 2
            elif rank_align == "bottom":
                node["y"] = prev_y + max_height - node["height"] / 2
            else:
                node["y"] = prev_y + max_height / 2
        prev_y += max_height + rank_sep


# -- conflicts ---------------------------------------------------


def _add_conflict(conflicts, v, w):
    if v > w:
        v, w = w, v
    conflicts.setdefault(v, {})[w] = True


def _has_conflict(conflicts, v, w):
    if v > w:
        v, w = w, v
    return w in conflicts.get(v, {})


def _find_other_inner_segment_node(graph, v):
    if graph.node(v).get("dummy"):
        for u in graph.predecessors(v) or []:
            if graph.node(u).get("dummy"):
                return u
    return None


def _find_type1_conflicts(graph, layering):
    conflicts: dict = {}

    def visit_layer(prev_layer, layer):
        k0 = 0
        scan_pos = 0
        prev_len = len(prev_layer)
        last_node = layer[-1] if layer else None
        for i, v in enumerate(layer):
            w = _find_other_inner_segment_node(graph, v)
            k1 = graph.node(w)["order"] if w else prev_len
            if w or v == last_node:
                for scan_node in layer[scan_pos:i + 1]:
                    for u in graph.predecessors(scan_node) or []:
                        u_label = graph.node(u)
                        u_pos = u_label["order"]
                        if (u_pos < k0 or k1 < u_pos) and not (
                            u_label.get("dummy") and graph.node(scan_node).get("dummy")
                        ):
                            _add_conflict(conflicts, u, scan_node)
                scan_pos = i + 1
                k0 = k1
        return layer

    if layering:
        acc = layering[0]
        for layer in layering[1:]:
            acc = visit_layer(acc, layer)
    return conflicts


def _find_type2_conflicts(graph, layering):
    conflicts: dict = {}

    def scan(south, south_pos, south_end, prev_north_border, next_north_border):
        for i in range(south_pos, south_end):
            if i >= len(south):
                continue
            v = south[i]
            if graph.node(v).get("dummy"):
                for u in graph.predecessors(v) or []:
                    u_node = graph.node(u)
                    if u_node.get("dummy") and (
                        u_node["order"] < prev_north_border or u_node["order"] > next_north_border
                    ):
                        _add_conflict(conflicts, u, v)

    def visit_layer(north, south):
        prev_north_pos = -1
        next_north_pos = -1
        south_pos = 0
        for south_lookahead, v in enumerate(south):
            if graph.node(v).get("dummy") == "border":
                preds = graph.predecessors(v)
                if preds:
                    next_north_pos = graph.node(preds[0])["order"]
                    scan(south, south_pos, south_lookahead, prev_north_pos, next_north_pos)
                    south_pos = south_lookahead
                    prev_north_pos = next_north_pos
            scan(south, south_pos, len(south), next_north_pos, len(north))
        return south

    if layering:
        acc = layering[0]
        for layer in layering[1:]:
            acc = visit_layer(acc, layer)
    return conflicts


# -- alignment / compaction ---------------------------------


def _vertical_alignment(graph, layering, conflicts, neighbor_fn):
    root: dict = {}
    align: dict = {}
    pos: dict = {}

    for layer in layering:
        for order, v in enumerate(layer):
            root[v] = v
            align[v] = v
            pos[v] = order

    for layer in layering:
        prev_idx = -1
        for v in layer:
            ws = neighbor_fn(v)
            if ws:
                ws = sorted(ws, key=lambda a: pos.get(a, 0))
                mp = (len(ws) - 1) / 2
                for i in range(math.floor(mp), math.ceil(mp) + 1):
                    if i >= len(ws):
                        continue
                    w = ws[i]
                    pos_w = pos.get(w)
                    if (
                        pos_w is not None
                        and align[v] == v
                        and prev_idx < pos_w
                        and not _has_conflict(conflicts, v, w)
                    ):
                        align[w] = v
                        align[v] = root[v] = root[w]
                        prev_idx = pos_w
    return {"root": root, "align": align}


def _sep(node_sep, edge_sep, reverse_sep):
    def fn(g, v, w):
        v_label = g.node(v)
        w_label = g.node(w)
        total = v_label["width"] / 2
        delta = None
        if "labelpos" in v_label:
            lp = str(v_label["labelpos"]).lower()
            if lp == "l":
                delta = -v_label["width"] / 2
            elif lp == "r":
                delta = v_label["width"] / 2
        if delta:
            total += delta if reverse_sep else -delta
        delta = None

        total += (edge_sep if v_label.get("dummy") else node_sep) / 2
        total += (edge_sep if w_label.get("dummy") else node_sep) / 2

        total += w_label["width"] / 2
        if "labelpos" in w_label:
            lp = str(w_label["labelpos"]).lower()
            if lp == "l":
                delta = w_label["width"] / 2
            elif lp == "r":
                delta = -w_label["width"] / 2
        if delta:
            total += delta if reverse_sep else -delta
        return total

    return fn


def _build_block_graph(graph, layering, root, reverse_sep):
    block_graph = Graph()
    label = graph.graph()
    sep_fn = _sep(label["nodesep"], label["edgesep"], reverse_sep)
    for layer in layering:
        u = None
        for v in layer:
            v_root = root[v]
            block_graph.setNode(v_root)
            if u is not None:
                u_root = root[u]
                prev_max = block_graph.edge(u_root, v_root)
                block_graph.setEdge(u_root, v_root, max(sep_fn(graph, v, u), prev_max or 0))
            u = v
    return block_graph


def _horizontal_compaction(graph, layering, root, align, reverse_sep=False):
    xs: dict = {}
    block_g = _build_block_graph(graph, layering, root, reverse_sep)
    border_type = "borderLeft" if reverse_sep else "borderRight"

    def iterate(set_xs, next_nodes):
        stack = block_g.nodes()[:]
        visited: dict = {}
        while stack:
            elem = stack.pop()
            if visited.get(elem):
                set_xs(elem)
            else:
                visited[elem] = True
                stack.append(elem)
                for nxt in next_nodes(elem):
                    stack.append(nxt)

    def pass1(elem):
        in_edges = block_g.inEdges(elem)
        if in_edges:
            acc = 0
            for e in in_edges:
                xs_v = xs.get(e["v"], 0)
                ew = block_g.edge(e)
                acc = max(acc, xs_v + (ew if ew is not None else 0))
            xs[elem] = acc
        else:
            xs[elem] = 0

    def pass2(elem):
        out_edges = block_g.outEdges(elem)
        mn = _INF
        if out_edges:
            for e in out_edges:
                xs_w = xs.get(e["w"], 0)
                ew = block_g.edge(e)
                mn = min(mn, xs_w - (ew if ew is not None else 0))
        node = graph.node(elem)
        if mn != _INF and node.get("borderType") != border_type:
            xs[elem] = max(xs.get(elem, 0), mn)

    iterate(pass1, lambda e: block_g.predecessors(e) or [])
    iterate(pass2, lambda e: block_g.successors(e) or [])

    for v in align:
        xs[v] = xs.get(root[v], 0)
    return xs


def _find_smallest_width_alignment(graph, xss):
    best = None
    best_width = _INF
    for xs in xss.values():
        mx = _NINF
        mn = _INF
        for v, x in xs.items():
            half = graph.node(v)["width"] / 2
            mx = max(x + half, mx)
            mn = min(x - half, mn)
        w = mx - mn
        if w < best_width:
            best_width = w
            best = xs
    return best


def _align_coordinates(xss, align_to):
    vals = list(align_to.values())
    lo = min(vals)
    hi = max(vals)
    for vert in ("u", "d"):
        for horiz in ("l", "r"):
            key = vert + horiz
            xs = xss.get(key)
            if not xs or xs is align_to:
                continue
            xs_vals = list(xs.values())
            if horiz == "l":
                delta = lo - min(xs_vals)
            else:
                delta = hi - max(xs_vals)
            if delta:
                xss[key] = {v: x + delta for v, x in xs.items()}


def _balance(xss, align=None):
    ul = xss.get("ul")
    if not ul:
        return {}
    result = {}
    for v, num in ul.items():
        if align:
            alt = xss.get(align.lower())
            if alt and alt.get(v) is not None:
                result[v] = alt[v]
                continue
        sorted_xs = sorted(xs.get(v, 0) for xs in xss.values())
        result[v] = (sorted_xs[1] + sorted_xs[2]) / 2 if len(sorted_xs) >= 4 else sorted_xs[0]
    return result


def position_x(graph):
    layering = build_layer_matrix(graph)
    conflicts = {}
    conflicts.update(_find_type1_conflicts(graph, layering))
    conflicts.update(_find_type2_conflicts(graph, layering))

    xss: dict = {}
    for vert in ("u", "d"):
        adjusted = layering if vert == "u" else list(reversed(layering))
        for horiz in ("l", "r"):
            if horiz == "r":
                adjusted = [list(reversed(inner)) for inner in adjusted]

            def neighbor_fn(v, _vert=vert):
                res = graph.predecessors(v) if _vert == "u" else graph.successors(v)
                return res or []

            align = _vertical_alignment(graph, adjusted, conflicts, neighbor_fn)
            xs = _horizontal_compaction(
                graph, adjusted, align["root"], align["align"], horiz == "r"
            )
            if horiz == "r":
                xs = {v: -x for v, x in xs.items()}
            xss[vert + horiz] = xs

    smallest = _find_smallest_width_alignment(graph, xss)
    _align_coordinates(xss, smallest)
    return _balance(xss, graph.graph().get("align"))
