# Ported from dagrejs/dagre (MIT). Mirrors lib/coordinate-system.ts.
"""``rankdir`` handling -- swap width/height for LR/RL before layout, and
reflect X/Y afterwards."""

from __future__ import annotations


def adjust(graph):
    rank_dir = (graph.graph().get("rankdir") or "").lower()
    if rank_dir in ("lr", "rl"):
        _swap_width_height(graph)


def undo(graph):
    rank_dir = (graph.graph().get("rankdir") or "").lower()
    if rank_dir in ("bt", "rl"):
        _reverse_y(graph)
    if rank_dir in ("lr", "rl"):
        _swap_xy(graph)
        _swap_width_height(graph)


def _swap_width_height(graph):
    for v in graph.nodes():
        _swap_wh_one(graph.node(v))
    for e in graph.edges():
        _swap_wh_one(graph.edge(e))


def _swap_wh_one(attrs):
    attrs["width"], attrs["height"] = attrs.get("height"), attrs.get("width")


def _reverse_y(graph):
    for v in graph.nodes():
        _reverse_y_one(graph.node(v))
    for e in graph.edges():
        label = graph.edge(e)
        for p in label.get("points") or []:
            _reverse_y_one(p)
        if "y" in label:
            _reverse_y_one(label)


def _reverse_y_one(attrs):
    attrs["y"] = -attrs["y"]


def _swap_xy(graph):
    for v in graph.nodes():
        _swap_xy_one(graph.node(v))
    for e in graph.edges():
        label = graph.edge(e)
        for p in label.get("points") or []:
            _swap_xy_one(p)
        if "x" in label:
            _swap_xy_one(label)


def _swap_xy_one(attrs):
    attrs["x"], attrs["y"] = attrs.get("y"), attrs.get("x")
