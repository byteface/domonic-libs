"""JS Playground: run JavaScript against domonic's live DOM.

Paste vanilla JS -- the acorn port parses it and the tree-walking evaluator in
``domonic_libs.acorn.interpret`` runs it against a fresh domonic
``<html><body>`` document plus ``console`` / ``Math`` / ``JSON`` / ``Array`` …
Whatever the script appends to ``document.body`` is a real domonic tree, shown
rendered, as HTML source, or as the parsed AST.
"""

import html as html_lib
import json

from domonic.events import Event
from domonic.html import (
    button,
    code,
    div,
    form,
    h1,
    h2,
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
from domonic_libs.acorn import parse
from domonic_libs.acorn.interpret import run_js

app = App("JS Playground", width=1180, height=768, text_select=True)
clipboard = Clipboard()

SAMPLES = {
    "hyperscript": (
        "// a tiny h() helper -- builds a real domonic tree\n"
        "function h(tag, props, ...kids) {\n"
        "  const el = document.createElement(tag);\n"
        "  for (const k in props) {\n"
        "    if (k === 'text') el.textContent = props[k];\n"
        "    else el.setAttribute(k, props[k]);\n"
        "  }\n"
        "  kids.forEach(c => el.appendChild(\n"
        "    typeof c === 'string' ? document.createTextNode(c) : c));\n"
        "  return el;\n"
        "}\n\n"
        "document.body.appendChild(\n"
        "  h('main', { class: 'card' },\n"
        "    h('h1', { text: 'Built by JS' }),\n"
        "    h('ul', {}, ...['parse', 'walk', 'append'].map(step =>\n"
        "      h('li', { text: step })))\n"
        "  )\n"
        ");\n"
        "console.log('rendered', document.body.childNodes.length, 'root node(s)');\n"
    ),
    "todo list": (
        "const todos = [\n"
        "  { text: 'Buy milk', done: true },\n"
        "  { text: 'Walk the dog', done: false },\n"
        "  { text: 'Ship acorn', done: false },\n"
        "];\n\n"
        "const ul = document.createElement('ul');\n"
        "for (const { text, done } of todos) {\n"
        "  const li = document.createElement('li');\n"
        "  li.textContent = (done ? '\\u2713 ' : '\\u2022 ') + text;\n"
        "  if (done) li.setAttribute('class', 'done');\n"
        "  ul.appendChild(li);\n"
        "}\n"
        "document.body.appendChild(ul);\n\n"
        "const open = todos.filter(t => !t.done).length;\n"
        "console.log(`${open} of ${todos.length} still open`);\n"
    ),
    "class component": (
        "class Badge {\n"
        "  constructor(label, count) {\n"
        "    this.label = label;\n"
        "    this.count = count;\n"
        "  }\n"
        "  render() {\n"
        "    const span = document.createElement('span');\n"
        "    span.setAttribute('class', 'badge');\n"
        "    span.textContent = `${this.label}: ${this.count}`;\n"
        "    return span;\n"
        "  }\n"
        "}\n\n"
        "const row = document.createElement('div');\n"
        "[['open', 3], ['closed', 12], ['draft', 1]].forEach(([l, c]) =>\n"
        "  row.appendChild(new Badge(l, c).render()));\n"
        "document.body.appendChild(row);\n"
        "console.log('badges:', row.childNodes.length);\n"
    ),
    "data → table": (
        "const rows = [\n"
        "  { name: 'Ada',   score: 99 },\n"
        "  { name: 'Alan',  score: 87 },\n"
        "  { name: 'Grace', score: 95 },\n"
        "];\n\n"
        "const table = document.createElement('table');\n"
        "const head = document.createElement('tr');\n"
        "['name', 'score'].forEach(h => {\n"
        "  const th = document.createElement('th');\n"
        "  th.textContent = h;\n"
        "  head.appendChild(th);\n"
        "});\n"
        "table.appendChild(head);\n\n"
        "rows.sort((a, b) => b.score - a.score).forEach(r => {\n"
        "  const tr = document.createElement('tr');\n"
        "  for (const key of ['name', 'score']) {\n"
        "    const td = document.createElement('td');\n"
        "    td.textContent = r[key];\n"
        "    tr.appendChild(td);\n"
        "  }\n"
        "  table.appendChild(tr);\n"
        "});\n"
        "document.body.appendChild(table);\n"
        "console.log('top score:', rows[0].score);\n"
    ),
    "CSSOM + events": (
        "// el.style / classList / addEventListener are domonic's real CSSOM +\n"
        "// event surface, reached straight through the evaluator.\n"
        "const panel = document.createElement('section');\n"
        "panel.classList.add('card');\n"
        "panel.style.setProperty('padding', '16px');\n"
        "panel.style.background = '#1e293b';\n\n"
        "let clicks = 0;\n"
        "panel.addEventListener('tap', () => {\n"
        "  clicks++;\n"
        "  console.log('tap', clicks);\n"
        "});\n"
        "panel.dispatchEvent(new Event('tap'));\n"
        "panel.dispatchEvent(new Event('tap'));\n\n"
        "const badge = document.createElement('span');\n"
        "badge.textContent = `taps: ${clicks}`;\n"
        "badge.style.color = '#38bdf8';\n"
        "panel.appendChild(badge);\n"
        "document.body.appendChild(panel);\n"
        "console.log('cssText:', panel.style.cssText);\n"
    ),
    "window API": (
        "// window forwards to domonic's real Window object\n"
        "console.log('base64:', window.atob('ZG9tb25pYw=='));\n"
        "console.log('location type:', typeof window.location);\n"
        "console.log('is global object:', window === globalThis);\n\n"
        "const box = window.document.createElement('div');\n"
        "box.setAttribute('class', 'card');\n"
        "box.textContent = 'built via window.document';\n"
        "window.document.body.appendChild(box);\n"
    ),
    "pure JS (no DOM)": (
        "const fib = n => n < 2 ? n : fib(n - 1) + fib(n - 2);\n"
        "console.log([...Array(10).keys()].map(fib).join(' '));\n\n"
        "const words = 'the quick brown fox'.split(' ');\n"
        "console.log(words.reduce((acc, w) => acc + w.length, 0), 'letters');\n\n"
        "try {\n"
        "  JSON.parse('{ bad json');\n"
        "} catch (e) {\n"
        "  console.log('caught:', e.name);\n"
        "}\n"
    ),
    "error + stack trace": (
        "// an uncaught throw reports its line and call stack\n"
        "function outer(x) {\n"
        "  return inner(x);\n"
        "}\n"
        "function inner(x) {\n"
        "  if (x < 0) throw new RangeError('x must be >= 0');\n"
        "  return Math.sqrt(x);\n"
        "}\n\n"
        "console.log(outer(9));\n"
        "console.log(outer(-1));\n"
    ),
    "async / await": (
        "// a real event loop -- microtasks before timers\n"
        "console.log('sync 1');\n"
        "setTimeout(() => console.log('timeout'), 0);\n"
        "Promise.resolve().then(() => console.log('microtask'));\n\n"
        "const wait = (ms) => new Promise((r) => setTimeout(r, ms));\n\n"
        "console.log('sync 2');\n\n"
        "async function run() {\n"
        "  const parts = await Promise.all([\n"
        "    wait(10).then(() => 'a'),\n"
        "    wait(5).then(() => 'b'),\n"
        "    Promise.resolve('c'),\n"
        "  ]);\n"
        "  console.log('all resolved:', parts.join(''));\n"
        "}\n"
        "run().then(() => console.log('done'));\n"
    ),
}

VIEWS = ["dom", "html", "console", "ast"]

state = {
    "sample": "hyperscript",
    "source": SAMPLES["hyperscript"],
    "view": "dom",
    "html": "",
    "console": "",
    "ast": "",
    "notes": "",
    "error": "",
}


def render(event=None):
    form_data = getattr(getattr(event, "target", None), "formData", None)
    previous = state["sample"]

    if form_data:
        for key in ("sample", "source", "view"):
            state[key] = getattr(form_data, key, state[key])

    if state["sample"] != previous:
        state["source"] = SAMPLES[state["sample"]]

    try:
        doc, lines = run_js(state["source"])
        state["html"] = str(doc.body)
        state["console"] = "\n".join(lines) or "(no console output)"
        tree = parse(state["source"], {"ecmaVersion": 2022}).to_dict()
        state["ast"] = json.dumps(tree, indent=2, default=str)
        n_nodes = _count(tree)
        state["notes"] = (
            f"{len(state['source'])} chars → {n_nodes} AST nodes, "
            f"{len(doc.body.childNodes)} DOM node(s) built, {len(lines)} console line(s)."
        )
        state["error"] = ""
    except Exception as exc:  # pragma: no cover - surfaced in the UI
        state["html"] = state["console"] = state["ast"] = ""
        state["notes"] = ""
        trace = getattr(exc, "js_trace", None)
        line = getattr(exc, "js_line", None)
        val = getattr(exc, "value", None)
        if isinstance(val, dict) and val.get("name"):
            head = f"{val['name']}: {val.get('message', '')}".rstrip(": ")
        else:
            head = f"{type(exc).__name__}: {exc}"
        if line:
            head += f"  (line {line})"
        state["error"] = head + (f"\n  at {trace}" if trace else "")


def _count(obj):
    n = 0
    if isinstance(obj, dict):
        n += "type" in obj
        for v in obj.values():
            n += _count(v)
    elif isinstance(obj, list):
        for v in obj:
            n += _count(v)
    return n


render()


def copy_out(event=None):
    payload = {"dom": state["html"], "html": state["html"],
               "console": state["console"], "ast": state["ast"]}[state["view"]]
    if payload:
        clipboard.writeText(payload)
        state["notes"] = "Copied to the clipboard."


def dispatch_click(event):
    if getattr(getattr(event, "target", None), "id", "") == "copy":
        copy_out(event)
    else:
        return False


def selected(value, current):
    return {"_selected": "selected"} if value == current else {}


def output_pane():
    if state["error"]:
        return pre(html_lib.escape(state["error"]), _class="out error")
    if state["view"] == "dom":
        node = div(_class="rendered")
        node.innerHTML = state["html"]
        return node
    text = {"html": state["html"], "console": state["console"], "ast": state["ast"]}[state["view"]]
    return pre(html_lib.escape(text), _class="out")


@app.route("/")
def index():
    sample = select(
        *(option(key, _value=key, **selected(key, state["sample"])) for key in SAMPLES),
        _name="sample", _title="Load a sample",
    )
    view = select(
        *(option(v.upper() if v in ("dom", "html", "ast") else v.title(), _value=v, **selected(v, state["view"])) for v in VIEWS),
        _name="view", _title="Output view",
    )

    workbench = form(
        div(
            div(
                h1("JS Playground"),
                p("acorn parses it, the tree-walking evaluator runs it against a live domonic document. What the script appends to document.body is a real Python object tree."),
                _class="title",
            ),
            div(view, sample, button("Copy", _type="button", _id="copy"), _class="actions"),
            _class="top",
        ),
        div(
            div(h2("JavaScript"), textarea(state["source"], _name="source", _spellcheck="false"), _class="pane"),
            div(h2(state["view"]), output_pane(), _class="pane"),
            _class="panes",
        ),
        div(
            span(state["notes"] or state["error"], _class="notes"),
            code("parse"), code("run_js"), code("document"),
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
body { margin: 0; background: #101418; color: #dbe3ea; font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
main { height: 100vh; box-sizing: border-box; padding: 14px; }
form { height: 100%; margin: 0; display: grid; grid-template-rows: auto 1fr auto; gap: 10px; }
.top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
h1 { margin: 0; font-size: 20px; color: #f4f7fa; }
h2 { margin: 0 0 6px; font-size: 11px; letter-spacing: .04em; text-transform: uppercase; color: #8b97a3; }
p { margin: 4px 0 0; color: #94a1ad; max-width: 720px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
select, button { height: 30px; margin: 0; font-size: 13px; background: #1c2530; color: #dbe3ea; border: 1px solid #303c48; border-radius: 6px; }
.panes { min-height: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.pane { min-height: 0; display: grid; grid-template-rows: auto 1fr; }
textarea, .out, .rendered { width: 100%; height: 100%; min-height: 0; box-sizing: border-box; margin: 0; padding: 14px; border: 1px solid #303c48; border-radius: 6px; background: #06090c; color: #dbe3ea; overflow: auto; }
textarea, .out { font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
textarea { resize: none; }
.out { white-space: pre-wrap; }
.out.error { color: #ff7b72; }
.rendered { background: #f7f9fb; color: #1f2328; line-height: 1.5; }
.rendered .card { max-width: 420px; }
.rendered ul { padding-left: 1.2em; }
.rendered table { border-collapse: collapse; }
.rendered th, .rendered td { border: 1px solid #c8d0da; padding: 5px 10px; text-align: left; }
.rendered .badge { display: inline-block; background: #e6eefb; color: #1b4079; border-radius: 999px; padding: 3px 10px; margin: 3px; font-size: 12px; }
.rendered .done { color: #6a7581; text-decoration: line-through; }
.status { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-height: 22px; color: #94a1ad; }
.status code { background: #12362f; color: #6ee7b7; border-radius: 999px; padding: 3px 8px; font-size: 12px; }
.notes { margin-right: auto; }
"""


if __name__ == "__main__":
    app.run()
