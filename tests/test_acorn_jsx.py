"""acorn-jsx port + the JSX -> domonic transform."""

import pytest

from domonic_libs.acorn.jsx import parse_jsx
from domonic_libs.acorn.jsx.transform import jsx_to_python


def _el(src):
    return parse_jsx(src, {"ecmaVersion": 2022}).to_dict()["body"][0]["expression"]


def test_parse_self_closing():
    el = _el("<Foo bar='x' n={1} flag />")
    assert el["type"] == "JSXElement"
    assert el["openingElement"]["selfClosing"] is True
    attrs = el["openingElement"]["attributes"]
    assert attrs[0]["value"]["value"] == "x"
    assert attrs[1]["value"]["expression"]["type"] == "Literal"
    assert attrs[2]["value"] is None


def test_parse_children_and_expression_container():
    el = _el("<div>a {b} <c/></div>")
    kinds = [c["type"] for c in el["children"]]
    assert kinds == ["JSXText", "JSXExpressionContainer", "JSXText", "JSXElement"]


def test_parse_fragment():
    el = _el("<><a/><b/></>")
    assert el["type"] == "JSXFragment"
    assert len(el["children"]) == 2


def test_parse_namespaced_and_member_names():
    assert _el("<ns:tag/>")["openingElement"]["name"]["type"] == "JSXNamespacedName"
    assert _el("<a.b.c/>")["openingElement"]["name"]["type"] == "JSXMemberExpression"


def test_parse_spread_attribute():
    el = _el("<X {...rest} y='1'/>")
    assert el["openingElement"]["attributes"][0]["type"] == "JSXSpreadAttribute"


def test_parse_entities():
    el = _el("<p>a &amp; b &#x26; c</p>")
    text = "".join(c.get("value", "") for c in el["children"] if c["type"] == "JSXText")
    assert "&" in text


@pytest.mark.parametrize("bad", [
    "<div>",                 # unterminated
    "<a></b>",               # mismatched closing tag
    "<a/><b/>",              # adjacent without wrapper
    "<x y={}/>",             # empty attribute expression
])
def test_parse_errors(bad):
    with pytest.raises(SyntaxError):
        parse_jsx(bad, {"ecmaVersion": 2022})


# -- transform -----------------------------------------------------------

@pytest.mark.parametrize("jsx, py", [
    ("<div/>", "div()"),
    ("<div className='x'>hi</div>", "div('hi', _class='x')"),
    ("<A n={x + 1} flag>{items}</A>", 'A(items, _n=x + 1, _flag="")'),
    ("<button onClick={go}>Go</button>", "button('Go', _onclick=go)"),
    ("<X {...p} a='1'/>", "X(_a='1', **p)"),
    ("<><a/><b/></>", "[a(), b()]"),
    ("<div style={{color:'red', fontSize: 12}}/>", "div(_style='color: red; font-size: 12px')"),
    ("<div style={{width: dyn}}/>", "div(_style={'width': dyn})"),  # non-literal -> dict
])
def test_transform_domonic(jsx, py):
    assert jsx_to_python(jsx) == py


def test_transform_h_mode():
    assert jsx_to_python("<App n={x}>{c}</App>", mode="h") == 'h("App", {"_n": x}, c)'


def test_transform_with_imports_roundtrips():
    jsx = "<main className='app'><h1>{t}</h1><ul>{rows}</ul></main>"
    py = jsx_to_python(jsx, with_imports=True)
    imports, expr = py.split("\n\n", 1)
    assert "from domonic.html import h1, main, ul" in imports
    ns = {"t": "Hi", "rows": ["x"]}
    exec(imports, ns)
    tree = eval(expr, ns)
    assert str(tree) == '<main class="app"><h1>Hi</h1><ul>x</ul></main>'


def test_transform_variable_declaration():
    out = jsx_to_python("const el = <section><Widget/></section>")
    assert out == "el = section(Widget())"


@pytest.mark.parametrize("jsx, py", [
    ("<div>{show && <span>x</span>}</div>", "div((span('x') if (show) else ''))"),
    ("<div>{ok ? <a>y</a> : <b>n</b>}</div>", "div((a('y') if (ok) else b('n')))"),
    ("<ul>{items.map(i => <li>{i}</li>)}</ul>", "ul([li(i) for i in items])"),
    ("<ul>{rows.map((r, n) => <li key={n}>{r}</li>)}</ul>",
     "ul([li(r, _key=n) for n, r in enumerate(rows)])"),
])
def test_transform_control_flow_children(jsx, py):
    assert jsx_to_python(jsx) == py


def test_transform_control_flow_executes():
    py = jsx_to_python("<ul>{items.map(i => <li>{i}</li>)}</ul>", with_imports=True)
    imports, expr = py.split("\n\n", 1)
    ns = {"items": ["a", "b"]}
    exec(imports, ns)
    assert str(eval(expr, ns)) == "<ul><li>a</li><li>b</li></ul>"
