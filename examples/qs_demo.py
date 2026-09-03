import json

from domonic.events import Event
from domonic.html import button, code, div, form, h1, h2, input, label, main, option, p, pre, select, span, style, textarea

from domonic_libs import App, on
from domonic_libs.qs import formats, parse, stringify


EXAMPLES = {
    "filters": "filters[status][]=open&filters[status][]=draft&filters[owner]=ada&page=2&sort=-updated",
    "dots": "user.name=Ada&user.roles[]=admin&user.roles[]=editor&flags.darkMode=true",
    "repeat": "tag=python&tag=domonic&tag=ports&limit=20",
    "comma": "ids=10,20,30&fields=name,email,created_at",
}

app = App("QS Workbench", width=1120, height=720, text_select=True)
state = {
    "sample": "filters",
    "query": EXAMPLES["filters"],
    "format": "RFC3986",
    "array_format": "indices",
    "allow_dots": True,
    "ignore_prefix": True,
    "json": "",
    "rebuilt": "",
    "notes": "",
    "error": "",
}


def selected(value, current):
    return {"_selected": "selected"} if value == current else {}


def checked(value):
    return {"_checked": "checked"} if value else {}


def bool_from_form(form_data, key, fallback):
    if form_data is None:
        return fallback
    return getattr(form_data, key, None) == "on"


def update(event=None):
    target = getattr(event, "target", None)
    form_data = getattr(target, "formData", None)
    old_sample = state["sample"]
    if form_data:
        state["sample"] = getattr(form_data, "sample", state["sample"])
        state["query"] = getattr(form_data, "query", state["query"])
        state["format"] = getattr(form_data, "format", state["format"])
        state["array_format"] = getattr(form_data, "array_format", state["array_format"])
        state["allow_dots"] = bool_from_form(form_data, "allow_dots", state["allow_dots"])
        state["ignore_prefix"] = bool_from_form(form_data, "ignore_prefix", state["ignore_prefix"])
    if state["sample"] != old_sample:
        state["query"] = EXAMPLES[state["sample"]]

    try:
        parsed = parse(
            state["query"],
            {
                "ignoreQueryPrefix": state["ignore_prefix"],
                "allowDots": state["allow_dots"],
                "comma": state["array_format"] == "comma",
            },
        )
        fmt = formats.RFC1738 if state["format"] == "RFC1738" else formats.RFC3986
        state["json"] = json.dumps(parsed, indent=2, sort_keys=True)
        state["rebuilt"] = stringify(
            parsed,
            {
                "arrayFormat": state["array_format"],
                "format": fmt,
                "addQueryPrefix": state["ignore_prefix"],
                "allowDots": state["allow_dots"],
            },
        )
        state["notes"] = (
            f"Parsed {len(parsed) if hasattr(parsed, '__len__') else 0} top-level key(s). "
            f"Stringified with {state['array_format']} arrays and {state['format']} encoding."
        )
        state["error"] = ""
    except Exception as exc:
        state["json"] = ""
        state["rebuilt"] = ""
        state["notes"] = "The parser rejected this shape before stringify could run."
        state["error"] = f"{type(exc).__name__}: {exc}"


update()


def checkbox(name, text, hint, value):
    return label(
        input(_name=name, _type="checkbox", **checked(value)),
        text,
        span(hint),
        _class="check",
    )


@app.route("/")
def index():
    sample = select(
        option("Nested filters", _value="filters", **selected("filters", state["sample"])),
        option("Dot notation", _value="dots", **selected("dots", state["sample"])),
        option("Repeated keys", _value="repeat", **selected("repeat", state["sample"])),
        option("Comma arrays", _value="comma", **selected("comma", state["sample"])),
        _name="sample",
        _title="Load query example",
    )
    array_format = select(
        option("indices", _value="indices", **selected("indices", state["array_format"])),
        option("brackets", _value="brackets", **selected("brackets", state["array_format"])),
        option("repeat", _value="repeat", **selected("repeat", state["array_format"])),
        option("comma", _value="comma", **selected("comma", state["array_format"])),
        _name="array_format",
        _title="Array stringify style",
    )
    encoding = select(
        option("RFC3986", _value="RFC3986", **selected("RFC3986", state["format"])),
        option("RFC1738", _value="RFC1738", **selected("RFC1738", state["format"])),
        _name="format",
        _title="Encoding format",
    )
    workbench = form(
        div(
            div(
                h1("QS Workbench"),
                p("Query strings are app state in URL form. Edit one side and watch qs rebuild the shareable version."),
                _class="title",
            ),
            div(sample, array_format, encoding, button("Round Trip", _type="submit"), _class="controls"),
            _class="top",
        ),
        div(
            checkbox("allow_dots", "Allow dots", "user.name becomes nested state", state["allow_dots"]),
            checkbox("ignore_prefix", "Ignore ?", "accepts ?page=2 as page=2", state["ignore_prefix"]),
            _class="toggles",
        ),
        div(
            div(h2("Query String"), textarea(state["query"], _name="query", _spellcheck="false"), _class="pane source"),
            div(h2("Parsed Object"), pre(state["error"] or state["json"], _class=("error" if state["error"] else "")), _class="pane"),
            div(h2("Rebuilt URL State"), pre(state["rebuilt"]), _class="pane"),
            div(h2("What Changed"), pre(state["notes"]), _class="pane"),
            _class="grid",
        ),
        div(code("parse"), code("stringify"), code("arrayFormat"), code("allowDots"), _class="chips"),
    )
    return main(
        style(
            """
            body { margin: 0; background: #f2f5f7; color: #202428; font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
            main { height: 100vh; box-sizing: border-box; padding: 14px; }
            form { height: 100%; display: grid; grid-template-rows: auto auto 1fr auto; gap: 12px; margin: 0; }
            .top { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
            h1 { margin: 0; font-size: 21px; }
            h2 { margin: 0 0 7px; color: #60707d; font-size: 12px; text-transform: uppercase; }
            p { margin: 4px 0 0; color: #53606b; max-width: 620px; }
            .controls, .toggles, .chips { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
            button, select { height: 30px; margin: 0; font-size: 13px; }
            .check { display: inline-flex; align-items: center; gap: 7px; background: #fff; border: 1px solid #ccd4dc; border-radius: 6px; padding: 7px 9px; }
            .check span { color: #64717c; font-size: 12px; }
            .grid { min-height: 0; display: grid; grid-template-columns: 1.15fr 1fr 1fr; grid-template-rows: 1fr 0.55fr; gap: 12px; }
            .pane { min-height: 0; display: grid; grid-template-rows: auto 1fr; }
            .source { grid-row: 1 / 3; }
            textarea, pre { width: 100%; height: 100%; min-height: 0; box-sizing: border-box; margin: 0; padding: 12px; border: 1px solid #c7d0da; border-radius: 6px; background: #fff; color: #1f2328; overflow: auto; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
            textarea { resize: none; }
            .error { color: #b42318; }
            .chips code { background: #e0ebdf; color: #245235; border-radius: 999px; padding: 4px 8px; font-size: 12px; }
            """
        ),
        on(on(on(workbench, Event.SUBMIT, update), Event.INPUT, update), Event.CHANGE, update),
    )


if __name__ == "__main__":
    app.run()
