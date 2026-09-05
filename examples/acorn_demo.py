"""Acorn Workbench: JavaScript in, ESTree out (and back).

Paste ECMAScript (or a whole module) and watch the faithful acorn port tokenize
and parse it live -- the AST as JSON, the token stream, a collapsed node-type
tree, or the source *regenerated* from the AST (pretty or minified). Switch the
``ecmaVersion`` and ``sourceType`` to see the grammar shift.
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
from domonic_libs.acorn import Tokenizer, generate, parse

app = App("Acorn Workbench", width=1180, height=768, text_select=True)
clipboard = Clipboard()

SAMPLES = {
    "arrow + destructuring": (
        "const distance = ({x: x1, y: y1}, {x: x2, y: y2}) =>\n"
        "  Math.hypot(x2 - x1, y2 - y1);\n\n"
        "const [head, ...tail] = [1, 2, 3, 4];\n"
    ),
    "class": (
        "class Counter extends Component {\n"
        "  #count = 0;\n"
        "  static defaults = { step: 1 };\n"
        "  get value() { return this.#count; }\n"
        "  inc(by = Counter.defaults.step) { this.#count += by; }\n"
        "  static { console.log('Counter ready'); }\n"
        "}\n"
    ),
    "module": (
        "import defaultExport, { named as alias } from './lib.js';\n"
        "export const version = '1.0.0';\n"
        "export default function main() {\n"
        "  return alias(defaultExport);\n"
        "}\n"
    ),
    "async / generators": (
        "async function* paginate(url) {\n"
        "  let next = url;\n"
        "  while (next) {\n"
        "    const page = await fetch(next).then(r => r.json());\n"
        "    yield* page.items;\n"
        "    next = page.next;\n"
        "  }\n"
        "}\n"
    ),
    "optional chaining + nullish": (
        "const city = user?.address?.city ?? 'unknown';\n"
        "const first = list?.[0]?.name;\n"
        "obj?.method?.();\n"
    ),
    "template + tagged": (
        "const q = sql`SELECT * FROM t WHERE id = ${id}`;\n"
        "const msg = `${greeting}, ${name.toUpperCase()}!`;\n"
    ),
}

VIEWS = ["ast", "tokens", "tree", "generate", "minify"]
ECMA = ["2015", "2020", "2022", "2025"]

state = {
    "sample": "arrow + destructuring",
    "source": SAMPLES["arrow + destructuring"],
    "view": "ast",
    "ecma": "2022",
    "module": False,
    "out": "",
    "notes": "",
    "error": "",
}


def _count_nodes(obj):
    n = 0
    if isinstance(obj, dict):
        if "type" in obj:
            n += 1
        for v in obj.values():
            n += _count_nodes(v)
    elif isinstance(obj, list):
        for v in obj:
            n += _count_nodes(v)
    return n


def _tree(obj, depth=0):
    lines = []
    if isinstance(obj, dict) and "type" in obj:
        label_bits = obj["type"]
        for k in ("name", "operator", "kind", "value", "raw"):
            if k in obj and not isinstance(obj[k], (dict, list)):
                label_bits += f"  {obj[k]!r}"
                break
        lines.append("  " * depth + label_bits)
        for v in obj.values():
            if isinstance(v, (dict, list)):
                lines += _tree(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            lines += _tree(v, depth)
    return lines


def render(event=None):
    form_data = getattr(getattr(event, "target", None), "formData", None)
    previous = state["sample"]

    if form_data:
        for key in ("sample", "source", "view", "ecma"):
            state[key] = getattr(form_data, key, state[key])
        state["module"] = getattr(form_data, "module", None) == "on"

    if state["sample"] != previous:
        state["source"] = SAMPLES[state["sample"]]

    opts = {
        "ecmaVersion": int(state["ecma"]),
        "sourceType": "module" if state["module"] else "script",
    }

    try:
        parsed = parse(state["source"], opts)
        tree = parsed.to_dict()
        toks = list(Tokenizer.tokenizer(state["source"], opts).tokenize())

        if state["view"] == "ast":
            state["out"] = json.dumps(tree, indent=2, default=str)
        elif state["view"] == "tokens":
            state["out"] = "\n".join(
                f"{t.type.label:<14} {t.value!r}" for t in toks if t.type.label != "eof"
            )
        elif state["view"] == "tree":
            state["out"] = "\n".join(_tree(tree))
        else:  # generate / minify -- AST back to source
            state["out"] = generate(parsed, minify=(state["view"] == "minify"))

        note = (
            f"{len(state['source'])} chars → {_count_nodes(tree)} AST nodes, "
            f"{len(toks) - 1} tokens. ES{state['ecma']}, {opts['sourceType']}."
        )
        if state["view"] in ("generate", "minify"):
            pct = 100 - round(100 * len(state["out"]) / max(1, len(state["source"])))
            note += f"  regenerated: {len(state['out'])} chars ({pct:+d}%)."
        state["notes"] = note
        state["error"] = ""
    except Exception as exc:  # pragma: no cover - surfaced in the UI
        state["out"] = ""
        state["notes"] = ""
        state["error"] = f"{type(exc).__name__}: {exc}"


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
    ecma = select(
        *(option("ES" + v, _value=v, **selected(v, state["ecma"])) for v in ECMA),
        _name="ecma", _title="ECMAScript version",
    )

    workbench = form(
        div(
            div(
                h1("Acorn Workbench"),
                p("A faithful acorn 8.18 port -- tokenizer + regex validator + recursive-descent parser -- running on domonic.javascript."),
                _class="title",
            ),
            div(
                view, ecma, sample,
                label(
                    input(_name="module", _type="checkbox", **checked(state["module"])),
                    span("module"), _class="toggle",
                ),
                button("Copy", _type="button", _id="copy"),
                _class="actions",
            ),
            _class="top",
        ),
        div(
            div(h2("JavaScript"), textarea(state["source"], _name="source", _spellcheck="false"), _class="pane"),
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
            code("parse"), code("Tokenizer"), code("ESTree"),
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
body { margin: 0; background: #1b1f24; color: #d7dde3; font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
main { height: 100vh; box-sizing: border-box; padding: 14px; }
form { height: 100%; margin: 0; display: grid; grid-template-rows: auto 1fr auto; gap: 10px; }
.top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
h1 { margin: 0; font-size: 20px; color: #f5f7fa; }
h2 { margin: 0 0 6px; font-size: 11px; letter-spacing: .04em; text-transform: uppercase; color: #8a95a1; }
p { margin: 4px 0 0; color: #9aa5b1; max-width: 680px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
select, button { height: 30px; margin: 0; font-size: 13px; background: #2b3138; color: #d7dde3; border: 1px solid #3a424b; border-radius: 6px; }
.toggle { display: inline-flex; align-items: center; gap: 6px; background: #2b3138; border: 1px solid #3a424b; border-radius: 6px; padding: 6px 10px; }
.panes { min-height: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.pane { min-height: 0; display: grid; grid-template-rows: auto 1fr; }
textarea, .out { width: 100%; height: 100%; min-height: 0; box-sizing: border-box; margin: 0; padding: 14px; border: 1px solid #3a424b; border-radius: 6px; background: #0f1216; color: #d7dde3; overflow: auto; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
textarea { resize: none; }
.out { white-space: pre; }
.out.error { color: #ff7b72; }
.status { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-height: 22px; color: #9aa5b1; }
.status code { background: #21323f; color: #7ee0c8; border-radius: 999px; padding: 3px 8px; font-size: 12px; }
.notes { margin-right: auto; }
"""


if __name__ == "__main__":
    app.run()
