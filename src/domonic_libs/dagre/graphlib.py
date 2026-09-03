# Ported from dagrejs/graphlib (MIT), tag 3.1.2-pre. Mirrors lib/graph.ts and
# the lib/alg helpers dagre uses.
"""A minimal port of graphlib -- the directed (optionally compound / multi)
graph ``dagre`` is built on.

Faithful to the upstream shape: nodes and edges carry arbitrary label objects,
edges are keyed by a ``(v, w, name)`` id, and the compound graph tracks a
parent/child tree. Only the pieces ``dagre`` touches are ported.
"""

from __future__ import annotations

_UNSET = object()
DEFAULT_EDGE_NAME = "\x00"
GRAPH_NODE = "\x00"
EDGE_KEY_DELIM = "\x01"


def _edge_args_to_id(is_directed, v, w, name=None):
    v, w = str(v), str(w)
    if not is_directed and v > w:
        v, w = w, v
    return v + EDGE_KEY_DELIM + w + EDGE_KEY_DELIM + (
        DEFAULT_EDGE_NAME if name is None else str(name)
    )


def _edge_args_to_obj(is_directed, v, w, name=None):
    v, w = str(v), str(w)
    if not is_directed and v > w:
        v, w = w, v
    obj = {"v": v, "w": w}
    if name:
        obj["name"] = name
    return obj


def _edge_obj_to_id(is_directed, edge_obj):
    return _edge_args_to_id(is_directed, edge_obj["v"], edge_obj["w"], edge_obj.get("name"))


def _inc(map_, k):
    map_[k] = map_.get(k, 0) + 1


def _dec(map_, k):
    if map_.get(k) is not None:
        map_[k] -= 1
        if not map_[k]:
            del map_[k]


class Graph:
    def __init__(self, opts=None):
        opts = opts or {}
        self._is_directed = opts.get("directed", True)
        self._is_multigraph = opts.get("multigraph", False)
        self._is_compound = opts.get("compound", False)

        self._label = None
        self._nodes: dict = {}
        self._in: dict = {}
        self._preds: dict = {}
        self._out: dict = {}
        self._sucs: dict = {}
        self._edge_objs: dict = {}
        self._edge_labels: dict = {}
        self._node_count = 0
        self._edge_count = 0
        self._default_node_label_fn = lambda v: None
        self._default_edge_label_fn = lambda v, w, name: None

        self._parent = None
        self._children = None
        if self._is_compound:
            self._parent = {}
            self._children = {GRAPH_NODE: {}}

    # -- graph -----------------------------------------------------------

    def isDirected(self):
        return self._is_directed

    def isMultigraph(self):
        return self._is_multigraph

    def isCompound(self):
        return self._is_compound

    def setGraph(self, label):
        self._label = label
        return self

    def graph(self):
        return self._label

    def setDefaultNodeLabel(self, label_or_fn):
        if callable(label_or_fn):
            self._default_node_label_fn = label_or_fn
        else:
            self._default_node_label_fn = lambda v: label_or_fn
        return self

    def setDefaultEdgeLabel(self, label_or_fn):
        if callable(label_or_fn):
            self._default_edge_label_fn = label_or_fn
        else:
            self._default_edge_label_fn = lambda v, w, name: label_or_fn
        return self

    # -- nodes ---------------------------------------------------------

    def nodeCount(self):
        return self._node_count

    def edgeCount(self):
        return self._edge_count

    def nodes(self):
        return list(self._nodes.keys())

    def sources(self):
        return [v for v in self.nodes() if not self._in[v]]

    def sinks(self):
        return [v for v in self.nodes() if not self._out[v]]

    def setNodes(self, names, label=_UNSET):
        for v in names:
            if label is _UNSET:
                self.setNode(v)
            else:
                self.setNode(v, label)
        return self

    def setNode(self, name, label=_UNSET):
        name = str(name)
        if name in self._nodes:
            if label is not _UNSET:
                self._nodes[name] = label
            return self
        self._nodes[name] = self._default_node_label_fn(name) if label is _UNSET else label
        if self._is_compound:
            self._parent[name] = GRAPH_NODE
            self._children[name] = {}
            self._children[GRAPH_NODE][name] = True
        self._in[name] = {}
        self._preds[name] = {}
        self._out[name] = {}
        self._sucs[name] = {}
        self._node_count += 1
        return self

    def node(self, name):
        return self._nodes.get(str(name))

    def hasNode(self, name):
        return str(name) in self._nodes

    def removeNode(self, name):
        name = str(name)
        if name in self._nodes:
            del self._nodes[name]
            if self._is_compound:
                self._remove_from_parents_child_list(name)
                del self._parent[name]
                for child in self.children(name):
                    self.setParent(child)
                del self._children[name]
            for e in list(self._in[name].keys()):
                self.removeEdge(self._edge_objs[e])
            del self._in[name]
            del self._preds[name]
            for e in list(self._out[name].keys()):
                self.removeEdge(self._edge_objs[e])
            del self._out[name]
            del self._sucs[name]
            self._node_count -= 1
        return self

    # -- compound ----------------------------------------------------

    def setParent(self, v, parent=None):
        if not self._is_compound:
            raise ValueError("Cannot set parent in a non-compound graph")
        v = str(v)
        if parent is None:
            parent = GRAPH_NODE
        else:
            parent = str(parent)
            ancestor = parent
            while ancestor is not None:
                if ancestor == v:
                    raise ValueError(
                        f"Setting {parent} as parent of {v} would create a cycle"
                    )
                ancestor = self.parent(ancestor)
            self.setNode(parent)
        self.setNode(v)
        self._remove_from_parents_child_list(v)
        self._parent[v] = parent
        self._children[parent][v] = True
        return self

    def parent(self, v):
        if self._is_compound:
            p = self._parent.get(str(v))
            if p != GRAPH_NODE:
                return p
        return None

    def children(self, v=GRAPH_NODE):
        v = str(v)
        if self._is_compound:
            kids = self._children.get(v)
            if kids is not None:
                return list(kids.keys())
            return []
        if v == GRAPH_NODE:
            return self.nodes()
        if self.hasNode(v):
            return []
        return []

    def _remove_from_parents_child_list(self, v):
        self._children[self._parent[v]].pop(v, None)

    # -- adjacency --------------------------------------------------

    def predecessors(self, v):
        p = self._preds.get(str(v))
        return list(p.keys()) if p is not None else None

    def successors(self, v):
        s = self._sucs.get(str(v))
        return list(s.keys()) if s is not None else None

    def neighbors(self, v):
        preds = self.predecessors(v)
        if preds is None:
            return None
        union = list(dict.fromkeys(preds + (self.successors(v) or [])))
        return union

    def isLeaf(self, v):
        nbrs = self.successors(v) if self.isDirected() else self.neighbors(v)
        return len(nbrs or []) == 0

    def filterNodes(self, fn):
        copy = Graph(
            {"directed": self._is_directed, "multigraph": self._is_multigraph,
             "compound": self._is_compound}
        )
        copy.setGraph(self.graph())
        for v, value in self._nodes.items():
            if fn(v):
                copy.setNode(v, value)
        for e in self._edge_objs.values():
            if copy.hasNode(e["v"]) and copy.hasNode(e["w"]):
                copy.setEdge(e, self.edge(e))

        parents: dict = {}

        def find_parent(v):
            p = self.parent(v)
            if not p or copy.hasNode(p):
                parents[v] = p
                return p
            if p in parents:
                return parents[p]
            return find_parent(p)

        if self._is_compound:
            for v in copy.nodes():
                copy.setParent(v, find_parent(v))
        return copy

    # -- edges -----------------------------------------------------

    def edges(self):
        return list(self._edge_objs.values())

    def setPath(self, nodes, label=_UNSET):
        prev = _UNSET
        for w in nodes:
            if prev is _UNSET:
                prev = w
                continue
            if label is _UNSET:
                self.setEdge(prev, w)
            else:
                self.setEdge(prev, w, label)
            prev = w
        return self

    def setEdge(self, v, w=_UNSET, value=_UNSET, name=None):
        value_specified = False
        if isinstance(v, dict) and "v" in v:
            v_str, w_str = v["v"], v["w"]
            name_str = v.get("name")
            if w is not _UNSET:
                edge_value = w
                value_specified = True
            else:
                edge_value = None
        else:
            v_str, w_str = v, w
            name_str = name
            if value is not _UNSET:
                edge_value = value
                value_specified = True
            else:
                edge_value = None

        v_str = str(v_str)
        w_str = str(w_str)
        if name_str is not None:
            name_str = str(name_str)

        e = _edge_args_to_id(self._is_directed, v_str, w_str, name_str)
        if e in self._edge_labels:
            if value_specified:
                self._edge_labels[e] = edge_value
            return self

        if name_str is not None and not self._is_multigraph:
            raise ValueError("Cannot set a named edge when isMultigraph = false")

        self.setNode(v_str)
        self.setNode(w_str)

        self._edge_labels[e] = (
            edge_value if value_specified
            else self._default_edge_label_fn(v_str, w_str, name_str)
        )

        edge_obj = _edge_args_to_obj(self._is_directed, v_str, w_str, name_str)
        v_str, w_str = edge_obj["v"], edge_obj["w"]

        self._edge_objs[e] = edge_obj
        _inc(self._preds[w_str], v_str)
        _inc(self._sucs[v_str], w_str)
        self._in[w_str][e] = edge_obj
        self._out[v_str][e] = edge_obj
        self._edge_count += 1
        return self

    def _edge_id(self, v, w=_UNSET, name=None):
        if w is _UNSET:
            return _edge_obj_to_id(self._is_directed, v)
        return _edge_args_to_id(self._is_directed, v, w, name)

    def edge(self, v, w=_UNSET, name=None):
        return self._edge_labels.get(self._edge_id(v, w, name))

    def hasEdge(self, v, w=_UNSET, name=None):
        return self._edge_id(v, w, name) in self._edge_labels

    def removeEdge(self, v, w=_UNSET, name=None):
        e = self._edge_id(v, w, name)
        edge = self._edge_objs.get(e)
        if edge:
            v_str, w_str = edge["v"], edge["w"]
            del self._edge_labels[e]
            del self._edge_objs[e]
            _dec(self._preds[w_str], v_str)
            _dec(self._sucs[v_str], w_str)
            del self._in[w_str][e]
            del self._out[v_str][e]
            self._edge_count -= 1
        return self

    def inEdges(self, v, w=None):
        if self.isDirected():
            return self._filter_edges(self._in.get(str(v)), v, w)
        return self.nodeEdges(v, w)

    def outEdges(self, v, w=None):
        if self.isDirected():
            return self._filter_edges(self._out.get(str(v)), v, w)
        return self.nodeEdges(v, w)

    def nodeEdges(self, v, w=None):
        v = str(v)
        if v in self._nodes:
            combined = {**self._in[v], **self._out[v]}
            return self._filter_edges(combined, v, w)
        return None

    @staticmethod
    def _filter_edges(set_v, local, remote=None):
        if set_v is None:
            return None
        edges = list(set_v.values())
        if not remote:
            return edges
        return [
            e for e in edges
            if (e["v"] == local and e["w"] == remote)
            or (e["v"] == remote and e["w"] == local)
        ]


# -- alg helpers -----------------------------------------------------


def components(graph):
    visited: dict = {}
    cmpts = []

    def dfs(v):
        if v in visited:
            return
        visited[v] = True
        cmpt.append(v)
        for w in graph.successors(v) or []:
            dfs(w)
        for w in graph.predecessors(v) or []:
            dfs(w)

    for v in graph.nodes():
        cmpt = []
        dfs(v)
        if cmpt:
            cmpts.append(cmpt)
    return cmpts


def _reduce(g, vs, order, fn, acc):
    if not isinstance(vs, list):
        vs = [vs]
    visited: dict = {}

    def navigation(v):
        return (g.successors(v) if g.isDirected() else g.neighbors(v)) or []

    def do_reduce(v, acc):
        if v not in visited:
            visited[v] = True
            if order != "post":
                acc = fn(acc, v)
            for w in navigation(v):
                acc = do_reduce(w, acc)
            if order == "post":
                acc = fn(acc, v)
        return acc

    for v in vs:
        if not g.hasNode(v):
            raise ValueError("Graph does not have node: " + v)
        acc = do_reduce(v, acc)
    return acc


def dfs(g, vs, order):
    def push(acc, v):
        acc.append(v)
        return acc

    return _reduce(g, vs, order, push, [])


def preorder(graph, vs):
    return dfs(graph, vs, "pre")


def postorder(graph, vs):
    return dfs(graph, vs, "post")


class CycleException(Exception):
    pass


def topsort(graph):
    visited: dict = {}
    stack: dict = {}
    results = []

    def visit(node):
        if node in stack:
            raise CycleException()
        if node not in visited:
            stack[node] = True
            visited[node] = True
            for p in graph.predecessors(node) or []:
                visit(p)
            del stack[node]
            results.append(node)

    for s in graph.sinks():
        visit(s)

    if len(visited) != graph.nodeCount():
        raise CycleException()
    return results
