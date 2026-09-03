"""Mermaid workbench: diagram text in, a domonic SVG tree out -- no JS, no binary.

Shows the Mermaid port (`domonic_libs.mermaid`): the sequence-diagram grammar,
`SequenceDB`, the loop / alt / opt / par / critical / break box machinery, pie
charts over domonic's `d3.shape`, and text measured through domonic's real
`getBBox()`. Type on the left, the rendered `<svg>` updates on the right.
"""

import re

from domonic.events import Event
from domonic.html import button, div, form, h1, main, option, p, select, span, style, textarea

from domonic_libs import App, on
from domonic_libs import mermaid

app = App("Mermaid Workbench", width=1240, height=820, text_select=True)

SAMPLES = {
    "handshake": (
        "sequenceDiagram\n"
        "    participant C as Client\n"
        "    participant S as Server\n"
        "    C->>+S: ClientHello\n"
        "    S-->>-C: ServerHello + cert\n"
        "    C->>S: key exchange\n"
        "    Note over C,S: channel encrypted\n"
        "    loop keep-alive every 30s\n"
        "        C->>S: ping\n"
        "        S--)C: pong\n"
        "    end\n"
        "    C-xS: close_notify\n"
    ),
    "order flow": (
        "sequenceDiagram\n"
        "    Customer->>Cart: add item\n"
        "    Cart->>Inventory: reserve stock\n"
        "    alt in stock\n"
        "        Inventory-->>Cart: reserved\n"
        "        Cart->>Payment: charge\n"
        "        Payment-->>Customer: receipt\n"
        "    else out of stock\n"
        "        Inventory-->>Cart: unavailable\n"
        "        Cart-->>Customer: sorry\n"
        "    end\n"
    ),
    "self call": (
        "sequenceDiagram\n"
        "    Worker->>Worker: poll queue\n"
        "    Worker->>DB: claim job\n"
        "    DB-->>Worker: job #4821\n"
        "    Worker->>Worker: run\n"
        "    Worker->>DB: mark done\n"
    ),
    "week": (
        "pie showData title Where the week went\n"
        '    "Building" : 22\n'
        '    "Meetings" : 9\n'
        '    "Review" : 6\n'
        '    "Writing" : 4\n'
        '    "Other" : 3\n'
    ),
    "languages": (
        "pie title Repo by language\n"
        '    "Python" : 68\n'
        '    "JavaScript" : 19\n'
        '    "CSS" : 8\n'
        '    "Shell" : 5\n'
    ),
    "pipeline": (
        "flowchart TD\n"
        "    A[Parse text] --> B{Diagram type?}\n"
        "    B -->|sequence / pie| C[Direct renderer]\n"
        "    B -->|flowchart| D[dagre layout]\n"
        "    C --> E[Emit SVG]\n"
        "    D --> E\n"
        "    E --> F((domonic tree))\n"
    ),
    "states": (
        "graph LR\n"
        "    idle((idle)) -->|start| running\n"
        "    running -->|pause| paused\n"
        "    paused -->|resume| running\n"
        "    running -->|stop| idle\n"
    ),
    "roadmap": (
        "timeline\n"
        "    title Port roadmap\n"
        "    section Shipped\n"
        "        Sequence : grammar : renderer : blocks\n"
        "        Pie : d3.shape\n"
        "        Timeline : you are here\n"
        "    section Next\n"
        "        gitGraph\n"
        "        dagre : flowcharts\n"
    ),
}

state = {
    "sample": "handshake",
    "source": SAMPLES["handshake"],
    "kind": "",
    "error": "",
    "svg": "",
    "notes": "",
}


def build(event=None):
    form_data = getattr(getattr(event, "target", None), "formData", None)
    previous = state["sample"]
    if form_data:
        state["sample"] = getattr(form_data, "sample", state["sample"])
        state["source"] = getattr(form_data, "source", state["source"])
    if state["sample"] != previous:
        state["source"] = SAMPLES[state["sample"]]

    try:
        element = mermaid.render_element(state["source"])
        state["kind"] = mermaid.detect_type(state["source"])
        state["svg"] = str(element)
        state["error"] = ""
        w = element.getAttribute("width")
        h = element.getAttribute("height")
        counts = []
        for label, pattern in (
            ("actors", r'class="actor actor-top"'),
            ("messages", r'class="messageText"'),
            ("blocks", r'class="labelText"'),
            ("notes", r'class="note"'),
            ("slices", r'class="pieCircle"'),
            ("nodes", r'class="timeline-node'),
            ("shapes", r"flow-node-group"),
        ):
            n = len(re.findall(pattern, state["svg"]))
            if n:
                counts.append(f"{n} {label}")
        state["notes"] = f"{state['kind']} diagram, {w}x{h}px  ·  " + ", ".join(counts)
    except Exception as exc:  # pragma: no cover - surfaced in the UI
        state["svg"] = ""
        state["notes"] = ""
        state["error"] = f"{type(exc).__name__}: {exc}"


build()


@app.route("/")
def index():
    picker = select(
        *[
            option(name, _value=name, **({"_selected": "selected"} if name == state["sample"] else {}))
            for name in SAMPLES
        ],
        _name="sample",
        _title="Load a sample",
    )

    preview = div(_class="preview")
    if state["svg"]:
        preview.innerHTML = state["svg"]
    else:
        preview.innerHTML = f'<p class="err">{state["error"]}</p>'

    editor = form(
        div(picker, button("Render", _type="submit"), _class="controls"),
        div(
            span("diagram source", _class="tag"),
            textarea(state["source"], _name="source", _spellcheck="false"),
            _class="pane source",
        ),
        _class="editor",
    )

    workbench = div(
        div(h1("Mermaid Workbench"), p("Diagram text becomes a domonic SVG tree in pure Python — no mermaid.js, no headless browser, no Graphviz."), _class="title"),
        div(
            on(on(editor, Event.SUBMIT, build), Event.CHANGE, build),
            div(
                div(span("rendered svg", _class="tag"), p(state["notes"] or state["error"], _class="notes"), _class="pane-head"),
                preview,
                _class="pane output",
            ),
            _class="grid",
        ),
        _class="wrap",
    )

    return main(style(CSS), workbench)


CSS = """
:root { --ground:#eef0ee; --surface:#ffffff; --ink:#20242b; --muted:#6b7280; --line:#d7dbd5; --accent:#3b6ea5; }
* { box-sizing: border-box; }
body { margin:0; background:var(--ground); color:var(--ink); font:14px/1.5 "IBM Plex Sans", system-ui, sans-serif; }
main { padding:20px; height:100vh; }
.wrap { display:flex; flex-direction:column; gap:16px; height:100%; }
h1 { margin:0; font-size:22px; letter-spacing:-0.01em; }
.title p { margin:4px 0 0; color:var(--muted); max-width:70ch; }
.grid { display:grid; grid-template-columns: minmax(320px, 420px) 1fr; gap:16px; min-height:0; flex:1; }
.editor { display:flex; flex-direction:column; gap:12px; min-height:0; }
.controls { display:flex; gap:8px; }
select, button { font:13px "IBM Plex Sans", sans-serif; height:32px; border:1px solid var(--line); border-radius:7px; background:var(--surface); color:var(--ink); padding:0 10px; }
button { background:var(--accent); color:#fff; border-color:var(--accent); cursor:pointer; padding:0 16px; }
.pane { background:var(--surface); border:1px solid var(--line); border-radius:10px; display:flex; flex-direction:column; min-height:0; overflow:hidden; }
.pane.source { flex:1; }
.tag { font:11px "IBM Plex Mono", monospace; text-transform:uppercase; letter-spacing:0.08em; color:var(--muted); padding:10px 12px 6px; }
textarea { margin:0; padding:0 12px 12px; font:13px/1.6 "IBM Plex Mono", ui-monospace, monospace; color:var(--ink); white-space:pre; overflow:auto; flex:1; outline:none; border:0; background:transparent; resize:none; }
textarea:focus { background:#fbfcfb; }
.output { min-height:0; }
.pane-head { display:flex; align-items:baseline; justify-content:space-between; gap:12px; padding-right:12px; }
.notes { margin:0; font:11px "IBM Plex Mono", monospace; color:var(--muted); padding:10px 0 6px; }
.preview { flex:1; overflow:auto; display:flex; align-items:center; justify-content:center; padding:20px; background:
  repeating-linear-gradient(0deg, transparent 0 23px, rgba(59,110,165,0.06) 23px 24px),
  repeating-linear-gradient(90deg, transparent 0 23px, rgba(59,110,165,0.06) 23px 24px); }
.preview svg { max-width:100%; height:auto; }
.err, .preview .err { color:#b5502f; font:13px "IBM Plex Mono", monospace; }
"""


if __name__ == "__main__":
    app.run()
