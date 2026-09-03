"""Marked workbench: Markdown in, HTML out, rendered live.

Shows the faithful marked.js port -- the ``gfm`` / ``breaks`` / ``pedantic``
options, the rendered preview, the raw HTML, and the lexer token tree, all
updating as you type.
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
from domonic_libs.marked import Lexer, marked

app = App("Marked Workbench", width=1180, height=768, text_select=True)
clipboard = Clipboard()

SAMPLES = {
    "guide": (
        "# Marked\n\n"
        "A **fast**, _faithful_ Markdown parser. See the "
        "[spec](https://spec.commonmark.org) for details.\n\n"
        "## Lists\n\n"
        "1. first\n2. second\n   - nested\n   - items\n3. third\n\n"
        "> Blockquotes work too.\n> Even across lines.\n\n"
        "```python\ndef greet(name):\n    return f\"hi {name}\"\n```\n\n"
        "Inline `code`, a footnote-ish [link][ref], and ~~strikethrough~~.\n\n"
        "[ref]: https://example.com \"Reference link\"\n"
    ),
    "gfm table": (
        "## Benchmark\n\n"
        "| Input | Old | New |\n"
        "| :---- | --: | --: |\n"
        "| 10 KB | 120ms | 40ms |\n"
        "| 1 MB | 9.1s | 3.0s |\n\n"
        "Autolinks like https://example.com become links under GFM.\n"
    ),
    "task list": (
        "### Checklist\n\n"
        "- [x] Port the lexer\n"
        "- [x] Port the tokenizer\n"
        "- [ ] Write the docs\n"
    ),
    "line breaks": (
        "With `breaks` off, a single newline\n"
        "stays in the same paragraph.\n\n"
        "Turn `breaks` on to render each newline as a <br>.\n"
    ),
    "raw html": (
        "Markdown allows <em>inline HTML</em> and blocks:\n\n"
        "<div class=\"callout\">\n  <strong>Note:</strong> this passes through.\n</div>\n"
    ),
}

VIEWS = ["preview", "html", "tokens"]

state = {
    "sample": "guide",
    "markdown": SAMPLES["guide"],
    "view": "preview",
    "gfm": True,
    "breaks": False,
    "pedantic": False,
    "html": "",
    "tokens": "",
    "notes": "",
    "error": "",
}


def render(event=None):
    form_data = getattr(getattr(event, "target", None), "formData", None)
    previous_sample = state["sample"]

    if form_data:
        for key in ("sample", "markdown", "view"):
            state[key] = getattr(form_data, key, state[key])
        state["gfm"] = getattr(form_data, "gfm", None) == "on"
        state["breaks"] = getattr(form_data, "breaks", None) == "on"
        state["pedantic"] = getattr(form_data, "pedantic", None) == "on"

    if state["sample"] != previous_sample:
        state["markdown"] = SAMPLES[state["sample"]]

    options = {
        "gfm": state["gfm"],
        "breaks": state["breaks"],
        "pedantic": state["pedantic"],
    }

    try:
        state["html"] = marked(state["markdown"], options)
        tokens = Lexer.lex(state["markdown"], dict(options))
        state["tokens"] = json.dumps(tokens, indent=2, default=str)
        block_count = sum(1 for t in tokens if t.get("type"))
        state["notes"] = (
            f"{len(state['markdown'])} chars Markdown → {len(state['html'])} chars "
            f"HTML, {block_count} top-level tokens. "
            f"gfm {'on' if state['gfm'] else 'off'}, "
            f"breaks {'on' if state['breaks'] else 'off'}, "
            f"pedantic {'on' if state['pedantic'] else 'off'}."
        )
        state["error"] = ""
    except Exception as exc:  # pragma: no cover - surfaced in the UI
        state["html"] = ""
        state["tokens"] = ""
        state["notes"] = ""
        state["error"] = f"{type(exc).__name__}: {exc}"


render()


def copy_html(event=None):
    if state["html"]:
        clipboard.writeText(state["html"])
        state["notes"] = "Copied HTML to the clipboard."


def save_html(event=None):
    if not state["html"]:
        return
    path = app.save_file(filename=f"{state['sample'].replace(' ', '-')}.html")
    path = path[0] if isinstance(path, (list, tuple)) and path else path
    if not path:
        return
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(state["html"])
    state["notes"] = f"Saved {path}"


def dispatch_click(event):
    target_id = getattr(getattr(event, "target", None), "id", "")
    if target_id == "copy":
        copy_html(event)
    elif target_id == "save":
        save_html(event)
    else:
        return False


def selected(value, current):
    return {"_selected": "selected"} if value == current else {}


def checked(value):
    return {"_checked": "checked"} if value else {}


def toggle(name, text, hint):
    return label(
        input(_name=name, _type="checkbox", **checked(state[name])),
        span(text),
        span(hint, _class="hint"),
        _class="toggle",
    )


def output_pane():
    if state["error"]:
        return pre(html_lib.escape(state["error"]), _class="out error")
    if state["view"] == "preview":
        # marked returns an HTML string; drop it into the preview verbatim
        node = div(_class="rendered")
        node.innerHTML = state["html"]
        return node
    # html / tokens views show the text escaped so it reads as source
    source = state["tokens"] if state["view"] == "tokens" else state["html"]
    return pre(html_lib.escape(source), _class="out")


@app.route("/")
def index():
    sample = select(
        *(option(key.title(), _value=key, **selected(key, state["sample"])) for key in SAMPLES),
        _name="sample",
        _title="Load a sample",
    )
    view = select(
        *(option(v.title(), _value=v, **selected(v, state["view"])) for v in VIEWS),
        _name="view",
        _title="Output view",
    )

    workbench = form(
        div(
            div(
                h1("Marked Workbench"),
                p("A faithful marked.js port. Edit the Markdown or a control and the output updates live."),
                _class="title",
            ),
            div(
                view,
                sample,
                button("Copy HTML", _type="button", _id="copy"),
                button("Save .html", _type="button", _id="save"),
                _class="actions",
            ),
            _class="top",
        ),
        div(
            toggle("gfm", "gfm", "tables, autolinks, ~~strike~~, task lists"),
            toggle("breaks", "breaks", "newline becomes <br>"),
            toggle("pedantic", "pedantic", "original Markdown.pl quirks"),
            _class="toggles",
        ),
        div(
            div(h2("Markdown"), textarea(state["markdown"], _name="markdown", _spellcheck="false"), _class="pane"),
            div(h2(state["view"]), output_pane(), _class="pane"),
            _class="panes",
        ),
        div(
            span(state["notes"] or state["error"], _class="notes"),
            code("marked"),
            code("Lexer.lex"),
            code("gfm"),
            code("pedantic"),
            _class="status",
        ),
    )

    return main(
        style(
            """
            body { margin: 0; background: #eef2f5; color: #1f2328; font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
            main { height: 100vh; box-sizing: border-box; padding: 14px; }
            form { height: 100%; margin: 0; display: grid; grid-template-rows: auto auto 1fr auto; gap: 10px; }
            .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
            h1 { margin: 0; font-size: 20px; }
            h2 { margin: 0 0 6px; font-size: 11px; letter-spacing: .04em; text-transform: uppercase; color: #64717c; }
            p { margin: 4px 0 0; color: #53606b; max-width: 640px; }
            .actions { display: flex; gap: 8px; flex-wrap: wrap; }
            .toggles { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; }
            select, button { height: 30px; margin: 0; font-size: 13px; background: #fff; color: #1f2328; }
            .toggle { display: inline-flex; align-items: center; gap: 6px; background: #fff; border: 1px solid #ccd4dc; border-radius: 6px; padding: 6px 10px; }
            .toggle .hint { color: #7b8791; font-size: 11px; }
            .panes { min-height: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
            .pane { min-height: 0; display: grid; grid-template-rows: auto 1fr; }
            textarea, .out, .rendered { width: 100%; height: 100%; min-height: 0; box-sizing: border-box; margin: 0; padding: 14px; border: 1px solid #c7d0da; border-radius: 6px; background: #fff; color: #1f2328; overflow: auto; }
            textarea, .out { font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
            textarea { resize: none; }
            .out { white-space: pre-wrap; }
            .out.error { color: #b42318; }
            .rendered { line-height: 1.55; }
            .rendered h1, .rendered h2, .rendered h3 { line-height: 1.25; margin: 1.1em 0 .5em; }
            .rendered h1 { font-size: 1.7em; } .rendered h2 { font-size: 1.35em; } .rendered h3 { font-size: 1.15em; }
            .rendered pre { background: #0d1117; color: #e6edf3; padding: 12px; border-radius: 6px; overflow: auto; }
            .rendered code { background: #eef1f4; padding: .1em .35em; border-radius: 4px; font-size: .9em; }
            .rendered pre code { background: none; padding: 0; }
            .rendered blockquote { margin: 1em 0; padding: 0 1em; border-left: 3px solid #c7d0da; color: #57606a; }
            .rendered table { border-collapse: collapse; margin: 1em 0; }
            .rendered th, .rendered td { border: 1px solid #c7d0da; padding: 6px 10px; }
            .rendered img { max-width: 100%; }
            .status { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-height: 22px; color: #53606b; }
            .status code { background: #e0ebdf; color: #245235; border-radius: 999px; padding: 3px 8px; font-size: 12px; }
            .notes { margin-right: auto; }
            """
        ),
        on(
            on(
                on(
                    on(workbench, Event.SUBMIT, render),
                    Event.INPUT,
                    render,
                ),
                Event.CHANGE,
                render,
            ),
            Event.CLICK,
            dispatch_click,
        ),
    )


if __name__ == "__main__":
    app.run()
