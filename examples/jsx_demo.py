"""JSX Workbench: JSX in, domonic Python out (and rendered).

Paste JSX and watch the acorn-jsx port + the ``jsx_to_python`` transform rewrite
the markup layer to ``domonic.html`` factories -- or to the Preact port's
``h(...)``. The "rendered" view actually runs the generated Python against a
small demo namespace and shows the domonic HTML it builds.
"""

import html as html_lib
import json
import traceback

from domonic.events import Event
from domonic.html import (
    button,
    code,
    div,
    form,
    h1,
    h2,
    input,
    label,
    main,
    option,
    p,
    pre,
    select,
    span,
    style,
    textarea,
)
from domonic.webapi.clipboard import Clipboard

from domonic_libs import App, on
from domonic_libs.acorn.jsx import parse_jsx
from domonic_libs.acorn.jsx.transform import jsx_to_python

app = App("JSX Workbench", width=1180, height=768, text_select=True)
clipboard = Clipboard()

SAMPLES = {
    "card": (
        "<article className=\"card\">\n"
        "  <h2>{title}</h2>\n"
        "  <p className=\"body\">{summary}</p>\n"
        "  <a href={url}>Read more</a>\n"
        "</article>\n"
    ),
    "list + expr": (
        "<ul className=\"feed\">\n"
        "  {rows}\n"
        "  <li className=\"more\" onClick={load_more}>Load more…</li>\n"
        "</ul>\n"
    ),
    "component + spread": (
        "<Layout {...layout_props}>\n"
        "  <Sidebar active={route} />\n"
        "  <Content>{children}</Content>\n"
        "</Layout>\n"
    ),
    "fragment": (
        "<>\n"
        "  <dt>{term}</dt>\n"
        "  <dd>{definition}</dd>\n"
        "</>\n"
    ),
    "style object": (
        "<div style={{padding: 24, background: '#1e293b', borderRadius: 8}}>\n"
        "  <span style={{fontWeight: 700, color: accent}}>{label_text}</span>\n"
        "</div>\n"
    ),
    "svg": (
        "<svg width=\"120\" height=\"120\">\n"
        "  <circle cx={60} cy={60} r={radius} fill={colour} />\n"
        "</svg>\n"
    ),
    "control flow": (
        "<ul className=\"todos\">\n"
        "  {items.map((item, i) => (\n"
        "    <li key={i} className={item.done ? 'done' : 'open'}>\n"
        "      {item.done && <span className=\"tick\">✓</span>}\n"
        "      {item.label}\n"
        "    </li>\n"
        "  ))}\n"
        "</ul>\n"
    ),
}

VIEWS = ["python", "rendered", "ast"]

# demo values so the "rendered" view can exec the generated Python. Components
# are stand-ins that just wrap their children in a <div data-component>.
def _stub(name):
    from domonic.html import div
    return lambda *a, **k: div(*a, **{"_data-component": name})


DEMO_NS = {
    "title": "Ada Lovelace", "summary": "Wrote the first algorithm.",
    "url": "/ada", "rows": ["<li>one</li>", "<li>two</li>"],
    "load_more": lambda *_: None,
    "route": "home", "children": "…", "layout_props": {"_id": "layout"},
    "Layout": _stub("Layout"), "Sidebar": _stub("Sidebar"), "Content": _stub("Content"),
    "term": "JSX", "definition": "an XML-ish syntax for elements",
    "accent": "#38bdf8", "label_text": "Tag", "radius": 40, "colour": "#38bdf8",
    "items": [
        type("I", (), {"label": "Ship it", "done": True})(),
        type("I", (), {"label": "Write docs", "done": False})(),
    ],
}

state = {
    "sample": "card",
    "source": SAMPLES["card"],
    "view": "python",
    "mode": False,       # False = domonic factories, True = h(...)
    "imports": True,
    "out": "",
    "notes": "",
    "error": "",
}


def render(event=None):
    form_data = getattr(getattr(event, "target", None), "formData", None)
    previous = state["sample"]

    if form_data:
        for key in ("sample", "source", "view"):
            state[key] = getattr(form_data, key, state[key])
        state["mode"] = getattr(form_data, "mode", None) == "on"
        state["imports"] = getattr(form_data, "imports", None) == "on"

    if state["sample"] != previous:
        state["source"] = SAMPLES[state["sample"]]

    mode = "h" if state["mode"] else "domonic"

    try:
        py = jsx_to_python(state["source"], mode=mode, with_imports=state["imports"])
        el_count = _count(parse_jsx(state["source"], {"ecmaVersion": 2022}).to_dict())

        if state["view"] == "python":
            state["out"] = py
        elif state["view"] == "ast":
            state["out"] = json.dumps(
                parse_jsx(state["source"], {"ecmaVersion": 2022}).to_dict()["body"][0],
                indent=2, default=str,
            )
        else:
            state["out"] = _run(py)

        state["notes"] = (
            f"{el_count} JSX elements → {len(py.splitlines())} lines of "
            f"{'h()' if state['mode'] else 'domonic'} Python."
        )
        state["error"] = ""
    except Exception as exc:  # pragma: no cover - surfaced in the UI
        state["out"] = ""
        state["notes"] = ""
        state["error"] = f"{type(exc).__name__}: {exc}"


def _count(obj):
    n = 0
    if isinstance(obj, dict):
        if obj.get("type") in ("JSXElement", "JSXFragment"):
            n += 1
        for v in obj.values():
            n += _count(v)
    elif isinstance(obj, list):
        for v in obj:
            n += _count(v)
    return n


def _run(py):
    """Exec the generated Python against DEMO_NS and serialise the result."""
    import domonic.html as _h
    import domonic.svg as _s

    ns = {n: getattr(_h, n) for n in dir(_h) if not n.startswith("_")}
    ns.update({n: getattr(_s, n) for n in dir(_s) if not n.startswith("_")})
    ns.update(DEMO_NS)
    from domonic_libs.preact import h  # for h() mode
    ns["h"] = h

    imports, _, expr = py.partition("\n\n")
    expr = expr or imports
    if not expr or expr is imports:
        imports, expr = "", py
    try:
        if imports:
            exec(imports, ns)
        head = expr.split("(", 1)[0]
        if "=" in head and head.split("=")[0].strip().isidentifier():
            exec(expr, ns)
            node = ns.get(head.split("=", 1)[0].strip())
        else:
            node = eval(expr, ns)
        return str(node)
    except Exception:
        return "// could not render:\n" + traceback.format_exc(limit=2)


render()


def copy_out(event=None):
    if state["out"]:
        clipboard.writeText(state["out"])
        state["notes"] = "Copied output to the clipboard."


def dispatch_click(event):
    if getattr(getattr(event, "target", None), "id", "") == "copy":
        copy_out(event)
    else:
        return False


def selected(value, current):
    return {"_selected": "selected"} if value == current else {}


def checked(value):
    return {"_checked": "checked"} if value else {}


@app.route("/")
def index():
    sample = select(
        *(option(key, _value=key, **selected(key, state["sample"])) for key in SAMPLES),
        _name="sample", _title="Load a sample",
    )
    view = select(
        *(option(v.title(), _value=v, **selected(v, state["view"])) for v in VIEWS),
        _name="view", _title="Output view",
    )

    workbench = form(
        div(
            div(
                h1("JSX Workbench"),
                p("acorn-jsx + the jsx_to_python transform. JS inside { … } passes through verbatim -- this rewrites the markup, not the JavaScript."),
                _class="title",
            ),
            div(
                view, sample,
                label(input(_name="mode", _type="checkbox", **checked(state["mode"])), span("h() mode"), _class="toggle"),
                label(input(_name="imports", _type="checkbox", **checked(state["imports"])), span("imports"), _class="toggle"),
                button("Copy", _type="button", _id="copy"),
                _class="actions",
            ),
            _class="top",
        ),
        div(
            div(h2("JSX"), textarea(state["source"], _name="source", _spellcheck="false"), _class="pane"),
            div(
                h2(state["view"]),
                pre(html_lib.escape(state["error"]), _class="out error") if state["error"]
                else pre(html_lib.escape(state["out"]), _class="out"),
                _class="pane",
            ),
            _class="panes",
        ),
        div(
            span(state["notes"] or state["error"], _class="notes"),
            code("parse_jsx"), code("jsx_to_python"), code("domonic.html"),
            _class="status",
        ),
    )

    return main(
        style(_CSS),
        on(
            on(
                on(
                    on(workbench, Event.SUBMIT, render),
                    Event.INPUT, render,
                ),
                Event.CHANGE, render,
            ),
            Event.CLICK, dispatch_click,
        ),
    )


_CSS = """
body { margin: 0; background: #0f172a; color: #e2e8f0; font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
main { height: 100vh; box-sizing: border-box; padding: 14px; }
form { height: 100%; margin: 0; display: grid; grid-template-rows: auto 1fr auto; gap: 10px; }
.top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
h1 { margin: 0; font-size: 20px; color: #f8fafc; }
h2 { margin: 0 0 6px; font-size: 11px; letter-spacing: .04em; text-transform: uppercase; color: #94a3b8; }
p { margin: 4px 0 0; color: #94a3b8; max-width: 700px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
select, button { height: 30px; margin: 0; font-size: 13px; background: #1e293b; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px; }
.toggle { display: inline-flex; align-items: center; gap: 6px; background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 6px 10px; }
.panes { min-height: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.pane { min-height: 0; display: grid; grid-template-rows: auto 1fr; }
textarea, .out { width: 100%; height: 100%; min-height: 0; box-sizing: border-box; margin: 0; padding: 14px; border: 1px solid #334155; border-radius: 6px; background: #020617; color: #e2e8f0; overflow: auto; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
textarea { resize: none; }
.out { white-space: pre-wrap; }
.out.error { color: #fb7185; }
.status { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-height: 22px; color: #94a3b8; }
.status code { background: #1e3a34; color: #6ee7b7; border-radius: 999px; padding: 3px 8px; font-size: 12px; }
.notes { margin-right: auto; }
"""


if __name__ == "__main__":
    app.run()
