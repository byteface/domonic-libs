# Ported from dagrejs/dagre + dagrejs/graphlib (MIT). Preserve the upstream
# licence when redistributing.
"""A faithful Python port of dagre -- directed-graph hierarchical layout.

    from domonic_libs.dagre import Graph, layout

    g = Graph({"multigraph": True, "compound": True})
    g.setGraph({"rankdir": "TB", "nodesep": 40, "ranksep": 40})
    g.setDefaultEdgeLabel(lambda *a: {})
    for v in ("a", "b", "c"):
        g.setNode(v, {"width": 60, "height": 30})
    g.setEdge("a", "b", {})
    g.setEdge("b", "c", {})
    layout(g)
    g.node("a")            # {'x': ..., 'y': ..., 'rank': 0, 'order': 0, ...}
    g.edge("a", "b")["points"]

The layout pipeline (acyclic -> nesting -> rank -> normalize -> order ->
position) mirrors ``dagre/lib/layout.ts`` file-for-file. Per-cluster ``rankdir``
recursion is not ported; single-``rankdir`` compound graphs work via the
nesting-graph + border-segment machinery.
"""

from __future__ import annotations

from .graphlib import Graph, components, postorder, preorder, topsort
from .layout import layout

__all__ = ["Graph", "layout", "components", "topsort", "preorder", "postorder"]
