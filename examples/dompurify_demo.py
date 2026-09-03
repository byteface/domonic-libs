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

from domonic_libs import App, on
from domonic_libs.dompurify import DOMPurify


EXAMPLES = {
    "event": '<p onclick="alert(1)">Hello <img src="x" onerror="alert(2)"> <a href="javascript:alert(3)">bad link</a></p>',
    "svg": '<svg><circle r="20"></circle><script>alert(1)</script><a xlink:href="javascript:alert(2)">bad</a></svg>',
    "template": '<p data-x="{{ user.secret }}">Hi ${ name }</p><template><img src=x onerror=alert(1)></template>',
    "clobber": '<form><input name="parentNode" value="x"><button formaction="javascript:alert(1)">Save</button></form>',
}

PROFILES = {
    "default": {},
    "html": {"USE_PROFILES": {"html": True}},
    "svg": {"USE_PROFILES": {"svg": True, "svgFilters": True}},
    "math": {"USE_PROFILES": {"mathMl": True}},
}

app = App("DOMPurify Workbench", width=1120, height=760, text_select=True)
purifier = DOMPurify()
state = {
    "sample": "event",
    "profile": "default",
    "safe_templates": False,
    "named_props": False,
    "html": EXAMPLES["event"],
    "clean": "",
    "removed": "",
    "config": "",
    "status": "Sanitized current sample.",
}


def selected(value, current):
    return {"_selected": "selected"} if value == current else {}


def checked(value):
    return {"_checked": "checked"} if value else {}


def bool_from_form(form_data, key, fallback):
    if form_data is None:
        return fallback
    return getattr(form_data, key, None) == "on"


def checkbox(name, text, hint, value):
    return label(
        input(_id=name, _name=name, _type="checkbox", **checked(value)),
        text,
        span(hint),
        _for=name,
    )


def config():
    cfg = dict(PROFILES[state["profile"]])
    if state["safe_templates"]:
        cfg["SAFE_FOR_TEMPLATES"] = True
    if state["named_props"]:
        cfg["SANITIZE_NAMED_PROPS"] = True
    return cfg


def update(event=None):
    target = getattr(event, "target", None)
    form_data = getattr(target, "formData", None)
    old_sample = state["sample"]
    if form_data:
        state["sample"] = getattr(form_data, "sample", state["sample"])
        state["profile"] = getattr(form_data, "profile", state["profile"])
        state["safe_templates"] = bool_from_form(form_data, "safe_templates", state["safe_templates"])
        state["named_props"] = bool_from_form(form_data, "named_props", state["named_props"])
        state["html"] = getattr(form_data, "html", state["html"])
    if state["sample"] != old_sample:
        state["html"] = EXAMPLES[state["sample"]]

    cfg = config()
    state["clean"] = purifier.sanitize(state["html"], cfg)
    state["removed"] = json.dumps(purifier.removed, indent=2, default=str)
    state["config"] = json.dumps(cfg or {"profile": "default allowlists"}, indent=2)
    state["status"] = "Sanitized current input."


update()


@app.route("/")
def index():
    sample = select(
        option("Event handlers + URLs", _value="event", **selected("event", state["sample"])),
        option("SVG namespace", _value="svg", **selected("svg", state["sample"])),
        option("Template expressions", _value="template", **selected("template", state["sample"])),
        option("DOM clobbering", _value="clobber", **selected("clobber", state["sample"])),
        _name="sample",
        _title="Load sample",
    )
    profile = select(
        option("Default HTML + SVG + MathML", _value="default", **selected("default", state["profile"])),
        option("HTML only", _value="html", **selected("html", state["profile"])),
        option("SVG only", _value="svg", **selected("svg", state["profile"])),
        option("MathML only", _value="math", **selected("math", state["profile"])),
        _name="profile",
        _title="Sanitizer profile",
    )
    workbench = form(
        div(
            div(
                h1("DOMPurify Workbench"),
                p("Paste hostile HTML, switch policy knobs, then sanitize. Typing is not re-rendered, so the editor stays steady."),
                _class="title",
            ),
            div(sample, profile, button("Sanitize", _type="submit"), _class="controls"),
            _class="top",
        ),
        div(
            checkbox("safe_templates", "Safe for templates", "strip {{ }}, <% %>, and ${ }", state["safe_templates"]),
            checkbox("named_props", "Sanitize named props", "prefix id/name to avoid DOM clobbering", state["named_props"]),
            _class="toggles",
        ),
        p(state["status"], _class="status"),
        div(
            textarea(state["html"], _name="html", _spellcheck="false"),
            div(h2("Clean HTML"), pre(state["clean"]), _class="pane"),
            div(h2("Removed"), pre(state["removed"]), _class="pane"),
            div(h2("Config"), pre(state["config"]), _class="pane"),
            _class="grid",
        ),
        div(
            code("USE_PROFILES"),
            code("SAFE_FOR_TEMPLATES"),
            code("SANITIZE_NAMED_PROPS"),
            code("uponSanitizeAttribute"),
            _class="chips",
        ),
    )
    return main(
        style(
            """
            body { margin: 0; background: #eef1f4; color: #202428; font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
            main { height: 100vh; box-sizing: border-box; padding: 14px; }
            form { height: 100%; display: grid; grid-template-rows: auto auto auto 1fr auto; gap: 12px; margin: 0; }
            .top { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
            h1 { margin: 0; font-size: 21px; }
            h2 { margin: 0 0 7px; font-size: 12px; color: #5f6b76; text-transform: uppercase; }
            p { margin: 4px 0 0; color: #53606b; max-width: 620px; }
            .controls, .toggles, .chips { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
            button, select { height: 30px; margin: 0; font-size: 13px; background: #fff; color: #1f2328; }
            .toggles label { display: inline-flex; align-items: center; gap: 6px; background: #fff; border: 1px solid #ccd4dc; border-radius: 6px; padding: 7px 9px; }
            .toggles span { color: #65717d; font-size: 12px; }
            .status { margin: 0; color: #53606b; font-size: 12px; }
            .grid { min-height: 0; display: grid; grid-template-columns: 1.2fr 1fr 1fr; grid-template-rows: 1fr 0.7fr; gap: 12px; }
            textarea { grid-row: 1 / 3; resize: none; }
            textarea, pre { width: 100%; height: 100%; min-height: 0; margin: 0; box-sizing: border-box; padding: 12px; border: 1px solid #c8d1dc; border-radius: 6px; background: #fff; color: #1f2328; overflow: auto; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
            .pane { min-height: 0; display: grid; grid-template-rows: auto 1fr; }
            .chips code { background: #dce7f3; color: #1d405c; border-radius: 999px; padding: 4px 8px; font-size: 12px; }
            """
        ),
        on(on(workbench, Event.SUBMIT, update), Event.CHANGE, update),
    )


if __name__ == "__main__":
    app.run()
