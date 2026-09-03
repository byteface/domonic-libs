"""Tests for the dagre + graphlib port.

Structural / invariant checks on the layout pipeline (dagre has no golden-output
fixtures -- coordinates vary with heuristics), plus the graphlib Graph API.
"""

import unittest

from domonic_libs.dagre import Graph, layout, topsort
from domonic_libs.dagre.graphlib import CycleException


class TestGraphlib(unittest.TestCase):
    def test_nodes_edges_adjacency(self):
        g = Graph()
        g.setEdge("a", "b")
        g.setEdge("b", "c")
        self.assertEqual(sorted(g.nodes()), ["a", "b", "c"])
        self.assertEqual(g.edgeCount(), 2)
        self.assertEqual(g.successors("a"), ["b"])
        self.assertEqual(g.predecessors("c"), ["b"])
        self.assertEqual(g.sources(), ["a"])
        self.assertEqual(g.sinks(), ["c"])

    def test_remove_node_drops_incident_edges(self):
        g = Graph()
        g.setEdge("a", "b")
        g.setEdge("b", "c")
        g.removeNode("b")
        self.assertEqual(g.edgeCount(), 0)
        self.assertEqual(sorted(g.nodes()), ["a", "c"])

    def test_edge_labels(self):
        g = Graph()
        g.setEdge("a", "b", {"weight": 3})
        self.assertEqual(g.edge("a", "b"), {"weight": 3})
        g.setEdge("a", "b", {"weight": 5})
        self.assertEqual(g.edge("a", "b")["weight"], 5)

    def test_compound_parent_child(self):
        g = Graph({"compound": True})
        g.setParent("n1", "cluster")
        g.setParent("n2", "cluster")
        self.assertEqual(g.parent("n1"), "cluster")
        self.assertEqual(sorted(g.children("cluster")), ["n1", "n2"])

    def test_topsort_and_cycle(self):
        g = Graph()
        g.setPath(["a", "b", "c"])
        self.assertEqual(topsort(g), ["a", "b", "c"])
        g.setEdge("c", "a")
        with self.assertRaises(CycleException):
            topsort(g)


def _new_graph(rankdir="TB"):
    g = Graph({"multigraph": True, "compound": True})
    g.setGraph({"rankdir": rankdir, "nodesep": 30, "ranksep": 30})
    g.setDefaultEdgeLabel(lambda *a: {})
    return g


class TestLayout(unittest.TestCase):
    def test_chain_ranks_increase_downward(self):
        g = _new_graph()
        for v in ("a", "b", "c"):
            g.setNode(v, {"width": 40, "height": 20})
        g.setEdge("a", "b", {})
        g.setEdge("b", "c", {})
        layout(g)
        ya, yb, yc = (g.node(v)["y"] for v in ("a", "b", "c"))
        self.assertLess(ya, yb)
        self.assertLess(yb, yc)
        self.assertLess(g.node("a")["rank"], g.node("c")["rank"])

    def test_diamond_middle_nodes_share_a_rank(self):
        g = _new_graph()
        for v in ("a", "b", "c", "d"):
            g.setNode(v, {"width": 40, "height": 20})
        for e in (("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")):
            g.setEdge(*e, {})
        layout(g)
        self.assertEqual(g.node("b")["rank"], g.node("c")["rank"])
        self.assertNotEqual(g.node("b")["x"], g.node("c")["x"])
        self.assertAlmostEqual(g.node("a")["x"], g.node("d")["x"], delta=1)

    def test_lr_layout_ranks_run_horizontally(self):
        g = _new_graph("LR")
        for v in ("a", "b", "c"):
            g.setNode(v, {"width": 40, "height": 20})
        g.setPath(["a", "b", "c"])
        for e in (("a", "b"), ("b", "c")):
            g.setEdge(*e, {})
        layout(g)
        self.assertLess(g.node("a")["x"], g.node("c")["x"])

    def test_edges_get_a_points_polyline(self):
        g = _new_graph()
        g.setNode("a", {"width": 40, "height": 20})
        g.setNode("b", {"width": 40, "height": 20})
        g.setEdge("a", "b", {})
        layout(g)
        pts = g.edge("a", "b")["points"]
        self.assertGreaterEqual(len(pts), 2)
        self.assertTrue(all("x" in p and "y" in p for p in pts))

    def test_graph_dimensions_cover_all_nodes(self):
        g = _new_graph()
        for v in ("a", "b", "c"):
            g.setNode(v, {"width": 40, "height": 20})
        g.setEdge("a", "b", {})
        g.setEdge("a", "c", {})
        layout(g)
        w = g.graph()["width"]
        h = g.graph()["height"]
        for v in g.nodes():
            n = g.node(v)
            self.assertLessEqual(n["x"] + n["width"] / 2, w + 1)
            self.assertLessEqual(n["y"] + n["height"] / 2, h + 1)

    def test_self_edge_does_not_crash(self):
        g = _new_graph()
        g.setNode("a", {"width": 40, "height": 20})
        g.setNode("b", {"width": 40, "height": 20})
        g.setEdge("a", "a", {})
        g.setEdge("a", "b", {})
        layout(g)
        self.assertIn("x", g.node("a"))


if __name__ == "__main__":
    unittest.main()
