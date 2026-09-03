"""Tests for the Preact port.

Preact's own suite is ~40 ``*.test.jsx`` files run in a browser under karma, so
it cannot execute here directly. This file ports a representative cross-section
of those scenarios -- ``render``, ``components``, ``keys``, ``fragments``,
``refs``, ``createContext`` and the ``hooks/`` suite -- to ``unittest``,
asserting on the real DOM that domonic builds.

HTML is compared through ``_norm``: it re-parses both sides so that domonic's
serialisation quirks (``<input/>`` vs ``<input>``, ``checked="true"`` vs
``checked=""``, attribute order) do not cause spurious failures, while text
content and element structure are preserved exactly.
"""

import unittest
from html.parser import HTMLParser

from domonic.dom import document
from domonic.events import Event

from domonic_libs.preact import (
    Component,
    Fragment,
    cloneElement,
    createContext,
    createRef,
    h,
    isValidElement,
    options,
    render,
    toChildArray,
)
from domonic_libs.preact.hooks import (
    useCallback,
    useContext,
    useEffect,
    useErrorBoundary,
    useId,
    useLayoutEffect,
    useMemo,
    useReducer,
    useRef,
    useState,
)

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_BOOL = {"checked", "selected", "disabled", "readonly", "multiple", "autofocus"}


class _Norm(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        parts = []
        for k, v in sorted(attrs):
            if k in _BOOL:
                parts.append(f' {k}=""')
            else:
                parts.append(f' {k}="{(v or "")}"')
        self.out.append(f"<{tag}{''.join(parts)}>")
        if tag in _VOID:
            pass

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        if tag not in _VOID:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(data)

    def handle_comment(self, data):
        self.out.append(f"<!--{data}-->")


def _norm(html):
    p = _Norm()
    p.feed(html or "")
    p.close()
    return "".join(p.out)


def _html(node):
    return "".join(str(c) for c in node.childNodes)


def scratch():
    return document.createElement("div")


class TestRender(unittest.TestCase):
    def test_renders_a_div(self):
        s = scratch()
        render(h("div", None), s)
        self.assertEqual(_norm(_html(s)), "<div></div>")

    def test_text_content(self):
        s = scratch()
        render(h("div", None, "Hello ", "World"), s)
        self.assertEqual(_norm(_html(s)), "<div>Hello World</div>")

    def test_attributes_and_props(self):
        s = scratch()
        render(h("div", {"id": "a", "class": "b c", "data-x": "1"}), s)
        self.assertEqual(_norm(_html(s)), '<div class="b c" data-x="1" id="a"></div>')

    def test_style_string(self):
        s = scratch()
        render(h("div", {"style": "color: red"}), s)
        self.assertIn("color", _html(s))

    def test_style_dict(self):
        s = scratch()
        render(h("div", {"style": {"color": "red", "marginTop": 5}}), s)
        out = _html(s)
        self.assertIn("color", out)
        self.assertIn("5px", out)

    def test_removes_orphaned_children(self):
        s = scratch()
        render(h("div", None, h("span", None, "1"), h("span", None, "2")), s)
        render(h("div", None, h("span", None, "1")), s)
        self.assertEqual(_norm(_html(s)), "<div><span>1</span></div>")

    def test_second_render_updates_in_place(self):
        s = scratch()
        render(h("h1", {"id": "a"}, "x"), s)
        first = s.childNodes[0]
        render(h("h1", {"id": "b"}, "y"), s)
        self.assertIs(s.childNodes[0], first)
        self.assertEqual(_norm(_html(s)), '<h1 id="b">y</h1>')

    def test_boolean_attribute(self):
        s = scratch()
        render(h("input", {"type": "checkbox", "checked": True}), s)
        self.assertEqual(_norm(_html(s)), '<input checked="" type="checkbox">')
        render(h("input", {"type": "checkbox", "checked": False}), s)
        self.assertEqual(_norm(_html(s)), '<input type="checkbox">')

    def test_name_prop_sets_attribute_not_tag(self):
        # domonic exposes a writable Element.name aliased to the tag name, so
        # `name` must go through setAttribute or `<input name="q">` renames to
        # `<q>` (see docs/domonic-wrinkles.md).
        s = scratch()
        render(h("input", {"type": "text", "name": "q"}), s)
        self.assertEqual(_norm(_html(s)), '<input name="q" type="text">')
        render(h("input", {"type": "text", "name": "r"}), s)
        self.assertEqual(_norm(_html(s)), '<input name="r" type="text">')

    def test_dangerously_set_inner_html(self):
        s = scratch()
        render(h("div", {"dangerouslySetInnerHTML": {"__html": "<b>x</b>"}}), s)
        self.assertEqual(_norm(_html(s)), "<div><b>x</b></div>")

    def test_none_and_bool_children_skipped(self):
        s = scratch()
        render(h("div", None, None, False, "keep", True), s)
        self.assertEqual(_norm(_html(s)), "<div>keep</div>")

    def test_nested_arrays_flattened(self):
        s = scratch()
        render(h("div", None, [h("i", None, "a"), [h("i", None, "b")]]), s)
        self.assertEqual(_norm(_html(s)), "<div><i>a</i><i>b</i></div>")


class TestComponents(unittest.TestCase):
    def test_function_component(self):
        s = scratch()

        def App(props):
            return h("p", None, "hi ", props["name"])

        render(h(App, {"name": "bob"}), s)
        self.assertEqual(_norm(_html(s)), "<p>hi bob</p>")

    def test_class_component_state(self):
        s = scratch()

        class Counter(Component):
            def __init__(self, props, ctx=None):
                super().__init__(props, ctx)
                self.state = {"n": 0}

            def render(self, props, state, context):
                return h(
                    "button",
                    {"onClick": lambda e: self.setState({"n": state["n"] + 1})},
                    str(state["n"]),
                )

        render(h(Counter, {}), s)
        self.assertEqual(_norm(_html(s)), "<button>0</button>")
        s.childNodes[0].dispatchEvent(Event("click"))
        self.assertEqual(_norm(_html(s)), "<button>1</button>")
        s.childNodes[0].dispatchEvent(Event("click"))
        self.assertEqual(_norm(_html(s)), "<button>2</button>")

    def test_lifecycle_order(self):
        s = scratch()
        log = []

        class C(Component):
            def componentWillMount(self):
                log.append("willMount")

            def componentDidMount(self):
                log.append("didMount")

            def componentWillUnmount(self):
                log.append("willUnmount")

            def render(self, p, st, c):
                return h("span", None, "c")

        def Wrap(props):
            return h("div", None, h(C, {}) if props["on"] else None)

        render(h(Wrap, {"on": True}), s)
        render(h(Wrap, {"on": False}), s)
        self.assertEqual(log, ["willMount", "didMount", "willUnmount"])

    def test_should_component_update_bails(self):
        s = scratch()
        renders = []

        class C(Component):
            def shouldComponentUpdate(self, np, ns, nc):
                return np["v"] != self.props["v"]

            def render(self, p, st, c):
                renders.append(p["v"])
                return h("span", None, str(p["v"]))

        render(h(C, {"v": 1}), s)
        render(h(C, {"v": 1}), s)
        render(h(C, {"v": 2}), s)
        self.assertEqual(renders, [1, 2])

    def test_context_via_class(self):
        s = scratch()

        class Provider(Component):
            def getChildContext(self):
                return {"color": "red"}

            def render(self, p, st, c):
                return h("div", None, p["children"])

        def Child(props, context):
            return h("span", None, context["color"])

        render(h(Provider, {}, h(Child, {})), s)
        self.assertEqual(_norm(_html(s)), "<div><span>red</span></div>")


class TestKeys(unittest.TestCase):
    def _list(self, items):
        return h("ul", None, *[h("li", {"key": k}, str(k)) for k in items])

    def test_reorder_preserves_nodes(self):
        s = scratch()
        render(self._list(["a", "b", "c"]), s)
        nodes = {n.textContent: n for n in s.childNodes[0].childNodes}
        render(self._list(["c", "a", "b"]), s)
        after = list(s.childNodes[0].childNodes)
        self.assertEqual([n.textContent for n in after], ["c", "a", "b"])
        self.assertIs(after[0], nodes["c"])
        self.assertIs(after[1], nodes["a"])

    def test_insert_and_remove(self):
        s = scratch()
        render(self._list([1, 2, 3]), s)
        render(self._list([1, 4, 2, 3]), s)
        self.assertEqual(
            [n.textContent for n in s.childNodes[0].childNodes], ["1", "4", "2", "3"]
        )
        render(self._list([4, 3]), s)
        self.assertEqual([n.textContent for n in s.childNodes[0].childNodes], ["4", "3"])


class TestFragments(unittest.TestCase):
    def test_fragment_children_hoisted(self):
        s = scratch()
        render(
            h("div", None, h(Fragment, None, h("a", None, "1"), h("b", None, "2"))), s
        )
        self.assertEqual(_norm(_html(s)), "<div><a>1</a><b>2</b></div>")

    def test_fragment_as_root(self):
        s = scratch()
        render(h(Fragment, None, h("p", None, "x"), h("p", None, "y")), s)
        self.assertEqual(_norm(_html(s)), "<p>x</p><p>y</p>")

    def test_to_child_array(self):
        arr = toChildArray([1, [2, [3, None]], False, "x"])
        self.assertEqual(arr, [1, 2, 3, "x"])


class TestRefs(unittest.TestCase):
    def test_callback_ref(self):
        s = scratch()
        seen = []
        render(h("input", {"ref": lambda el: seen.append(el)}), s)
        self.assertIs(seen[0], s.childNodes[0])

    def test_object_ref(self):
        s = scratch()
        ref = createRef()
        render(h("span", {"ref": ref}, "x"), s)
        self.assertIs(ref["current"], s.childNodes[0])

    def test_ref_detached_on_unmount(self):
        s = scratch()
        ref = createRef()
        render(h("span", {"ref": ref}, "x"), s)
        render(h("div", None), s)
        self.assertIsNone(ref["current"])


class TestCloneAndValidate(unittest.TestCase):
    def test_is_valid_element(self):
        self.assertTrue(isValidElement(h("div", None)))
        self.assertFalse(isValidElement({"type": "div"}))
        self.assertFalse(isValidElement(None))

    def test_clone_element_merges_props(self):
        s = scratch()
        base = h("div", {"class": "a", "id": "x"}, "child")
        render(cloneElement(base, {"class": "b"}), s)
        self.assertEqual(_norm(_html(s)), '<div class="b" id="x">child</div>')


class TestCreateContext(unittest.TestCase):
    def test_provider_consumer_updates(self):
        s = scratch()
        Ctx = createContext("default")

        def Leaf(props):
            return h("em", None, useContext(Ctx))

        def Tree(props):
            return h(Ctx.Provider, {"value": props["v"]}, h(Leaf, {}))

        render(h(Tree, {"v": "one"}), s)
        self.assertEqual(_norm(_html(s)), "<em>one</em>")
        render(h(Tree, {"v": "two"}), s)
        self.assertEqual(_norm(_html(s)), "<em>two</em>")

    def test_default_value_without_provider(self):
        s = scratch()
        Ctx = createContext("fallback")

        def Leaf(props):
            return h("em", None, useContext(Ctx))

        render(h(Leaf, {}), s)
        self.assertEqual(_norm(_html(s)), "<em>fallback</em>")

    def test_consumer_render_prop(self):
        s = scratch()
        Ctx = createContext("x")

        def Tree(props):
            return h(
                Ctx.Provider,
                {"value": "y"},
                h(Ctx.Consumer, None, lambda v: h("i", None, v)),
            )

        render(h(Tree, {}), s)
        self.assertEqual(_norm(_html(s)), "<i>y</i>")


class TestHooks(unittest.TestCase):
    def test_use_state(self):
        s = scratch()

        def C(props):
            n, setn = useState(0)
            return h("button", {"onClick": lambda e: setn(n + 1)}, str(n))

        render(h(C, {}), s)
        s.childNodes[0].dispatchEvent(Event("click"))
        s.childNodes[0].dispatchEvent(Event("click"))
        self.assertEqual(_norm(_html(s)), "<button>2</button>")

    def test_use_state_functional_update(self):
        s = scratch()

        def C(props):
            n, setn = useState(0)
            return h("button", {"onClick": lambda e: setn(lambda p: p + 10)}, str(n))

        render(h(C, {}), s)
        s.childNodes[0].dispatchEvent(Event("click"))
        self.assertEqual(_norm(_html(s)), "<button>10</button>")

    def test_use_state_bails_on_equal_value(self):
        s = scratch()
        renders = []

        def C(props):
            n, setn = useState(0)
            renders.append(n)
            return h("button", {"onClick": lambda e: setn(0)}, str(n))

        render(h(C, {}), s)
        s.childNodes[0].dispatchEvent(Event("click"))
        self.assertEqual(renders, [0])

    def test_use_reducer(self):
        s = scratch()

        def reducer(state, action):
            return state + 1 if action == "inc" else state

        def C(props):
            n, dispatch = useReducer(reducer, 0)
            return h("button", {"onClick": lambda e: dispatch("inc")}, str(n))

        render(h(C, {}), s)
        s.childNodes[0].dispatchEvent(Event("click"))
        s.childNodes[0].dispatchEvent(Event("click"))
        self.assertEqual(_norm(_html(s)), "<button>2</button>")

    def test_use_effect_runs_and_cleans_up(self):
        s = scratch()
        log = []

        def C(props):
            v = props["v"]

            def eff():
                log.append(("run", v))
                return lambda: log.append(("cleanup", v))

            useEffect(eff, [v])
            return h("span", None, str(v))

        render(h(C, {"v": 1}), s)
        render(h(C, {"v": 2}), s)
        render(h("div", None), s)
        self.assertEqual(log, [("run", 1), ("cleanup", 1), ("run", 2), ("cleanup", 2)])

    def test_use_effect_empty_deps_runs_once(self):
        s = scratch()
        count = []

        def C(props):
            useEffect(lambda: count.append(1), [])
            return h("span", None, str(props["v"]))

        render(h(C, {"v": 1}), s)
        render(h(C, {"v": 2}), s)
        render(h(C, {"v": 3}), s)
        self.assertEqual(count, [1])

    def test_use_layout_effect(self):
        s = scratch()
        log = []

        def C(props):
            useLayoutEffect(lambda: log.append("layout"), [])
            return h("span", None, "x")

        render(h(C, {}), s)
        self.assertEqual(log, ["layout"])

    def test_use_ref_stable(self):
        s = scratch()
        refs = []

        def C(props):
            r = useRef(0)
            refs.append(r)
            _, setn = useState(0)
            return h("button", {"onClick": lambda e: setn(props["v"])}, "x")

        render(h(C, {"v": 1}), s)
        s.childNodes[0].dispatchEvent(Event("click"))
        self.assertIs(refs[0], refs[1])

    def test_use_memo_recomputes_on_dep_change(self):
        s = scratch()
        calls = []

        def C(props):
            useMemo(lambda: calls.append(props["v"]) or props["v"], [props["v"]])
            return h("span", None, str(props["v"]))

        render(h(C, {"v": 1}), s)
        render(h(C, {"v": 1}), s)
        render(h(C, {"v": 2}), s)
        self.assertEqual(calls, [1, 2])

    def test_use_callback_identity(self):
        s = scratch()
        cbs = []

        def C(props):
            cb = useCallback(lambda: None, [props["dep"]])
            cbs.append(cb)
            return h("span", None, "x")

        render(h(C, {"dep": 1}), s)
        render(h(C, {"dep": 1}), s)
        render(h(C, {"dep": 2}), s)
        self.assertIs(cbs[0], cbs[1])
        self.assertIsNot(cbs[1], cbs[2])

    def test_use_id_stable_and_unique(self):
        s = scratch()
        ids = []

        def C(props):
            ids.append((useId(), useId()))
            return h("span", None, "x")

        render(h(C, {}), s)
        render(h(C, {}), s)
        self.assertNotEqual(ids[0][0], ids[0][1])
        self.assertEqual(ids[0], ids[1])

    def test_use_error_boundary(self):
        s = scratch()

        def Boom(props):
            raise ValueError("boom")

        def App(props):
            err, reset = useErrorBoundary()
            if err:
                return h("p", None, "caught: ", str(err))
            return h("div", None, h(Boom, {}))

        render(h(App, {}), s)
        self.assertEqual(_norm(_html(s)), "<p>caught: boom</p>")


class TestLifecycleExtras(unittest.TestCase):
    def test_get_derived_state_from_props(self):
        s = scratch()

        class C(Component):
            @staticmethod
            def getDerivedStateFromProps(props, state):
                return {"doubled": props["v"] * 2}

            def render(self, p, st, c):
                return h("span", None, str(st.get("doubled")))

        render(h(C, {"v": 3}), s)
        self.assertEqual(_norm(_html(s)), "<span>6</span>")
        render(h(C, {"v": 5}), s)
        self.assertEqual(_norm(_html(s)), "<span>10</span>")

    def test_component_did_update_receives_old_props(self):
        s = scratch()
        seen = []

        class C(Component):
            def componentDidUpdate(self, old_props, old_state, snapshot):
                seen.append((old_props["v"], self.props["v"]))

            def render(self, p, st, c):
                return h("span", None, str(p["v"]))

        render(h(C, {"v": 1}), s)
        render(h(C, {"v": 2}), s)
        render(h(C, {"v": 3}), s)
        self.assertEqual(seen, [(1, 2), (2, 3)])

    def test_force_update(self):
        s = scratch()
        external = {"v": 0}
        holder = {}

        class C(Component):
            def render(self, p, st, c):
                holder["self"] = self
                return h("span", None, str(external["v"]))

        render(h(C, {}), s)
        external["v"] = 9
        holder["self"].forceUpdate()
        self.assertEqual(_norm(_html(s)), "<span>9</span>")

    def test_class_component_did_catch(self):
        s = scratch()
        caught = []

        class Boundary(Component):
            def __init__(self, props, ctx=None):
                super().__init__(props, ctx)
                self.state = {"error": None}

            def componentDidCatch(self, error, info):
                caught.append(str(error))
                self.setState({"error": str(error)})

            def render(self, p, st, c):
                if st["error"]:
                    return h("p", None, "boundary: ", st["error"])
                return h("div", None, p["children"])

        def Boom(props):
            raise RuntimeError("kaboom")

        render(h(Boundary, {}, h(Boom, {})), s)
        self.assertEqual(caught, ["kaboom"])
        self.assertEqual(_norm(_html(s)), "<p>boundary: kaboom</p>")


class TestOptions(unittest.TestCase):
    def test_vnode_hook_fires(self):
        seen = []
        prev = options.vnode
        options.vnode = lambda vn: seen.append(vn.type)
        try:
            h("div", None, h("span", None))
        finally:
            options.vnode = prev
        self.assertIn("div", seen)
        self.assertIn("span", seen)


if __name__ == "__main__":
    unittest.main()
