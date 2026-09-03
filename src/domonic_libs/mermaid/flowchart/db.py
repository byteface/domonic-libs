# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Mirrors the parts
# of src/diagrams/flowchart/flowDb.ts the port uses.
"""``FlowDB`` -- vertices (id -> {text, shape}), directed edges, and subgraphs."""

from __future__ import annotations


class FlowDB:
    def __init__(self):
        self.clear()

    def clear(self):
        self.direction = "TB"
        self.vertices: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.subgraphs: list[dict] = []
        self._title = ""
        self._acc_title = ""
        self._acc_description = ""

    def set_direction(self, direction: str):
        self.direction = direction.upper()

    def add_vertex(self, vid: str, text=None, shape=None):
        vid = vid.strip()
        if not vid:
            return
        node = self.vertices.setdefault(vid, {"id": vid, "text": vid, "shape": "round"})
        if text is not None:
            node["text"] = text
        if shape is not None:
            node["shape"] = shape

    def add_link(self, starts, ends, link_info: dict, text: str = ""):
        for start in starts:
            self.add_vertex(start)
            for end in ends:
                self.add_vertex(end)
                self.edges.append(
                    {
                        "start": start,
                        "end": end,
                        "type": link_info["type"],
                        "stroke": link_info["stroke"],
                        "length": link_info.get("length", 1),
                        "text": text,
                    }
                )

    def add_subgraph(self, sid: str, node_ids: list[str], title: str):
        self.subgraphs.append({"id": sid or f"subGraph{len(self.subgraphs)}",
                               "nodes": list(node_ids), "title": title or sid})

    def set_diagram_title(self, value):
        self._title = value

    def get_diagram_title(self):
        return self._title

    def set_acc_title(self, value):
        self._acc_title = value.strip()

    def get_acc_title(self):
        return self._acc_title

    def set_acc_description(self, value):
        self._acc_description = value.strip()

    def get_acc_description(self):
        return self._acc_description
