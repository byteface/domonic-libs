"""Turndown workbench: HTML in, Markdown out, with every option live.

Shows the faithful turndown.js port -- all CommonMark options, the GFM plugin
(`domonic_libs.turndown.gfm`), and the `.keep` / `.remove` filters -- reacting
as you type or change a control.
"""

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
from domonic_libs.turndown import TurndownService
from domonic_libs.turndown.gfm import gfm

app = App("Turndown Workbench", width=1180, height=760, text_select=True)
clipboard = Clipboard()

SAMPLES = {
    "article": (
        "<h1>Release notes</h1>\n"
        "<p>The <strong>2.0</strong> release focuses on <em>speed</em>. Read the "
        "<a href=\"https://example.com/guide\" title=\"Upgrade guide\">guide</a> "
        "before upgrading.</p>\n"
        "<h2>Highlights</h2>\n"
        "<ul><li>Parser is ~3x faster</li>"
        "<li>New <code>--watch</code> flag</li>"
        "<li>Fixes <a href=\"https://example.com/i/42\">#42</a></li></ul>\n"
        "<blockquote><p>Upgrading was painless.</p><p>Shipped the same day.</p></blockquote>\n"
        "<pre><code class=\"language-python\">import thing\nthing.run(watch=True)\n</code></pre>"
    ),
    "gfm table": (
        "<h2>Benchmarks</h2>\n"
        "<table><thead><tr><th>Input</th><th align=\"right\">Old</th>"
        "<th align=\"right\">New</th></tr></thead>\n"
        "<tbody>\n"
        "<tr><td>10 KB</td><td align=\"right\">120ms</td><td align=\"right\">40ms</td></tr>\n"
        "<tr><td>1 MB</td><td align=\"right\">9.1s</td><td align=\"right\">3.0s</td></tr>\n"
        "</tbody></table>"
    ),
    "task list": (
        "<h2>Checklist</h2>\n"
        "<ul>\n"
        "<li><input type=\"checkbox\" checked>Write the port</li>\n"
        "<li><input type=\"checkbox\" checked>Port the fixture suite</li>\n"
        "<li><input type=\"checkbox\">Ship the demo</li>\n"
        "</ul>"
    ),
    "inline whitespace": (
        "<p>Turndown needs the space between "
        "<strong>bold</strong> <em>and</em> <a href=\"/x\">italic</a> to survive "
        "parsing &mdash; a spot where DOM parsers often disagree.</p>"
    ),
    "keep / remove": (
        "<p>Body text stays.</p>\n"
        "<aside class=\"promo\">Marketing block</aside>\n"
        "<p>An embed:</p>\n"
        "<iframe src=\"https://example.com/player\"></iframe>\n"
        "<p>Edited: <del>old wording</del> <ins>new wording</ins>.</p>"
    ),
}

CODE_OPTIONS = {
    "heading_style": ["atx", "setext"],
    "bullet_list_marker": ["-", "*", "+"],
    "code_block_style": ["fenced", "indented"],
    "fence": ["```", "~~~"],
    "em_delimiter": ["_", "*"],
    "strong_delimiter": ["**", "__"],
    "link_style": ["inlined", "referenced"],
    "link_reference_style": ["full", "collapsed", "shortcut"],
}

state = {
    "sample": "article",
    "html": SAMPLES["article"],
    "gfm": True,
    "preformatted_code": False,
    "keep": "",
    "remove": "",
    "markdown": "",
    "notes": "",
    "error": "",
}
state.update({name: choices[0] for name, choices in CODE_OPTIONS.items()})


def _tags(value):
    return [tag.strip() for tag in value.split(",") if tag.strip()]


def convert(event=None):
    form_data = getattr(getattr(event, "target", None), "formData", None)
    previous_sample = state["sample"]

    if form_data:
        for key in list(CODE_OPTIONS) + ["sample", "html", "keep", "remove"]:
            state[key] = getattr(form_data, key, state[key])
        state["gfm"] = getattr(form_data, "gfm", None) == "on"
        state["preformatted_code"] = getattr(form_data, "preformatted_code", None) == "on"

    if state["sample"] != previous_sample:
        state["html"] = SAMPLES[state["sample"]]
        # the "keep / remove" sample is only interesting with filters set
        state["keep"] = "iframe, ins" if state["sample"] == "keep / remove" else ""
        state["remove"] = "aside" if state["sample"] == "keep / remove" else ""

    try:
        service = TurndownService(
            **{name: state[name] for name in CODE_OPTIONS},
            preformatted_code=state["preformatted_code"],
        )
        if state["gfm"]:
            service.use(gfm)
        if _tags(state["keep"]):
            service.keep(_tags(state["keep"]))
        if _tags(state["remove"]):
            service.remove(_tags(state["remove"]))

        state["markdown"] = service.turndown(state["html"])
        line_count = state["markdown"].count("\n") + 1 if state["markdown"] else 0
        state["notes"] = (
            f"{len(state['html'])} chars HTML → {len(state['markdown'])} chars "
            f"Markdown, {line_count} lines. GFM {'on' if state['gfm'] else 'off'}."
        )
        state["error"] = ""
    except Exception as exc:  # pragma: no cover - surfaced in the UI
        state["markdown"] = ""
        state["notes"] = ""
        state["error"] = f"{type(exc).__name__}: {exc}"


convert()


def copy_markdown(event=None):
    if state["markdown"]:
        clipboard.writeText(state["markdown"])
        state["notes"] = "Copied Markdown to the clipboard."


def save_markdown(event=None):
    if not state["markdown"]:
        return
    path = app.save_file(filename=f"{state['sample'].replace(' ', '-')}.md")
    path = path[0] if isinstance(path, (list, tuple)) and path else path
    if not path:
        return
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(state["markdown"])
    state["notes"] = f"Saved {path}"


def dispatch_click(event):
    target_id = getattr(getattr(event, "target", None), "id", "")
    if target_id == "copy":
        copy_markdown(event)
    elif target_id == "save":
        save_markdown(event)
    else:
        return False


def selected(value, current):
    return {"_selected": "selected"} if value == current else {}


def checked(value):
    return {"_checked": "checked"} if value else {}


def option_select(name):
    return select(
        *(
            option(choice, _value=choice, **selected(choice, state[name]))
            for choice in CODE_OPTIONS[name]
        ),
        _name=name,
        _title=name.replace("_", " "),
    )


def field(name):
    return label(span(name.replace("_", " ")), option_select(name), _class="field")


def toggle(name, text, hint):
    return label(
        input(_name=name, _type="checkbox", **checked(state[name])),
        span(text),
        span(hint, _class="hint"),
        _class="toggle",
    )


@app.route("/")
def index():
    sample = select(
        *(
            option(key.title(), _value=key, **selected(key, state["sample"]))
            for key in SAMPLES
        ),
        _name="sample",
        _title="Load a sample",
    )

    workbench = form(
        div(
            div(
                h1("Turndown Workbench"),
                p("A faithful turndown.js port. Edit the HTML or a control and the Markdown updates live."),
                _class="title",
            ),
            div(sample, button("Copy", _type="button", _id="copy"), button("Save .md", _type="button", _id="save"), _class="actions"),
            _class="top",
        ),
        div(
            field("heading_style"),
            field("bullet_list_marker"),
            field("code_block_style"),
            field("fence"),
            field("em_delimiter"),
            field("strong_delimiter"),
            field("link_style"),
            field("link_reference_style"),
            _class="fields",
        ),
        div(
            toggle("gfm", "GFM", "tables, ~~strike~~, task lists"),
            toggle("preformatted_code", "preformattedCode", "keep whitespace in inline <code>"),
            label(span("keep"), input(_name="keep", _value=state["keep"], _placeholder="iframe, ins", _spellcheck="false"), _class="field"),
            label(span("remove"), input(_name="remove", _value=state["remove"], _placeholder="aside, style", _spellcheck="false"), _class="field"),
            _class="toggles",
        ),
        div(
            div(h2("HTML"), textarea(state["html"], _name="html", _spellcheck="false"), _class="pane"),
            div(
                h2("Markdown"),
                pre(state["error"] or state["markdown"], _class=("out error" if state["error"] else "out")),
                _class="pane",
            ),
            _class="panes",
        ),
        div(span(state["notes"] or state["error"], _class="notes"), code("TurndownService"), code(".use(gfm)"), code(".keep"), code(".remove"), _class="status"),
    )

    return main(
        style(
            """
            body { margin: 0; background: #eef2f5; color: #1f2328; font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
            main { height: 100vh; box-sizing: border-box; padding: 14px; }
            form { height: 100%; margin: 0; display: grid; grid-template-rows: auto auto auto 1fr auto; gap: 10px; }
            .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
            h1 { margin: 0; font-size: 20px; }
            h2 { margin: 0 0 6px; font-size: 11px; letter-spacing: .04em; text-transform: uppercase; color: #64717c; }
            p { margin: 4px 0 0; color: #53606b; max-width: 640px; }
            .actions { display: flex; gap: 8px; }
            .fields, .toggles { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: end; }
            .field { display: grid; gap: 3px; font-size: 11px; color: #64717c; text-transform: uppercase; letter-spacing: .03em; }
            .field input, select, button { height: 30px; margin: 0; font-size: 13px; background: #fff; color: #1f2328; }
            .field input { width: 150px; text-transform: none; padding: 0 8px; border: 1px solid #c7d0da; border-radius: 6px; }
            .toggle { display: inline-flex; align-items: center; gap: 6px; background: #fff; border: 1px solid #ccd4dc; border-radius: 6px; padding: 6px 10px; }
            .toggle .hint, .field .hint { color: #7b8791; font-size: 11px; text-transform: none; }
            .panes { min-height: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
            .pane { min-height: 0; display: grid; grid-template-rows: auto 1fr; }
            textarea, pre.out { width: 100%; height: 100%; min-height: 0; box-sizing: border-box; margin: 0; padding: 12px; border: 1px solid #c7d0da; border-radius: 6px; background: #fff; color: #1f2328; overflow: auto; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
            textarea { resize: none; }
            pre.out { white-space: pre-wrap; }
            pre.error { color: #b42318; }
            .status { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-height: 22px; color: #53606b; }
            .status code { background: #e0ebdf; color: #245235; border-radius: 999px; padding: 3px 8px; font-size: 12px; }
            .notes { margin-right: auto; }
            """
        ),
        on(
            on(
                on(
                    on(workbench, Event.SUBMIT, convert),
                    Event.INPUT,
                    convert,
                ),
                Event.CHANGE,
                convert,
            ),
            Event.CLICK,
            dispatch_click,
        ),
    )


if __name__ == "__main__":
    app.run()
