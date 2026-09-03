"""Validator workbench: type a value, see every validator.js check that matches.

Runs the whole ``domonic_libs.validator`` port live -- every ``is*`` validator
against one input, plus the sanitizers and converters -- as you type.
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
from domonic_libs import validator as v

app = App("Validator Workbench", width=1180, height=780, text_select=True)
clipboard = Clipboard()

SAMPLES = {
    "email": "ada.lovelace+work@example.co.uk",
    "url": "https://user@host.example.com:8443/path?q=1#frag",
    "iban": "DE89 3704 0044 0532 0130 00",
    "credit card": "4111 1111 1111 1111",
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.qzHc_bXls0",
    "hex colour": "#3aa1ff",
    "date": "2026-09-02T14:30:00Z",
    "money": "$1,234.56",
    "mac": "01:23:45:67:89:ab",
}

# is* validators that take only the value (skip the 4 that need a second arg)
AUTO_SKIP = {"isDivisibleBy", "isHash", "isIn", "isWhitelisted"}
VALIDATORS = sorted(
    n for n in v.__all__ if n.startswith("is") and n not in AUTO_SKIP
)

SANITIZERS = ["escape", "unescape", "trim", "ltrim", "rtrim", "stripLow", "normalizeEmail"]
CONVERTERS = ["toBoolean", "toInt", "toFloat", "toDate", "toString"]

state = {
    "sample": "email",
    "value": SAMPLES["email"],
    "chars": "aeiou",
    "matches": [],
    "misses": [],
    "sanitized": [],
    "notes": "",
}


def run(event=None):
    form_data = getattr(getattr(event, "target", None), "formData", None)
    previous = state["sample"]
    if form_data:
        for key in ("sample", "value", "chars"):
            state[key] = getattr(form_data, key, state[key])
    if state["sample"] != previous:
        state["value"] = SAMPLES[state["sample"]]

    value = state["value"]
    matches, misses = [], []
    for name in VALIDATORS:
        try:
            result = getattr(v, name)(value)
        except Exception:
            result = None
        (matches if result else misses).append(name)
    state["matches"], state["misses"] = matches, misses

    rows = []
    for name in SANITIZERS + CONVERTERS:
        try:
            fn = getattr(v, name)
            out = fn(value, state["chars"]) if name in ("blacklist", "whitelist") else fn(value)
        except Exception as exc:
            out = f"({type(exc).__name__})"
        rows.append((name, repr(out)))
    for name in ("blacklist", "whitelist"):
        try:
            out = getattr(v, name)(value, state["chars"])
        except Exception as exc:
            out = f"({type(exc).__name__})"
        rows.append((f"{name}({state['chars']!r})", repr(out)))
    state["sanitized"] = rows

    state["notes"] = (
        f"{len(matches)} of {len(VALIDATORS)} validators match "
        f"a {len(value)}-character value."
    )


run()


def dispatch_click(event):
    if getattr(getattr(event, "target", None), "id", "") == "copy":
        clipboard.writeText(", ".join(state["matches"]))
        state["notes"] = "Copied matching validator names."
    else:
        return False


def selected(value, current):
    return {"_selected": "selected"} if value == current else {}


@app.route("/")
def index():
    sample = select(
        *(option(k.title(), _value=k, **selected(k, state["sample"])) for k in SAMPLES),
        _name="sample",
        _title="Load a sample value",
    )

    workbench = form(
        div(
            div(
                h1("Validator Workbench"),
                p("A faithful validator.js port. Every is* check runs against the value as you type."),
                _class="title",
            ),
            div(sample, button("Copy matches", _type="button", _id="copy"), _class="actions"),
            _class="top",
        ),
        div(
            label(span("value"), input(_name="value", _value=state["value"], _spellcheck="false", _autocomplete="off"), _class="field grow"),
            label(span("blacklist / whitelist chars"), input(_name="chars", _value=state["chars"], _spellcheck="false"), _class="field"),
            _class="inputs",
        ),
        div(
            div(
                h2(f"matches ({len(state['matches'])})"),
                div(*(span(n, _class="chip yes") for n in state["matches"]) or [span("none", _class="empty")], _class="chips"),
                h2(f"no match ({len(state['misses'])})"),
                div(*(span(n, _class="chip no") for n in state["misses"]), _class="chips dim"),
                _class="pane",
            ),
            div(
                h2("sanitizers & converters"),
                pre(
                    "\n".join(f"{name:<28} {out}" for name, out in state["sanitized"]),
                    _class="out",
                ),
                _class="pane",
            ),
            _class="panes",
        ),
        div(span(state["notes"], _class="notes"), code("validator"), code("is*"), code("escape"), code("normalizeEmail"), _class="status"),
    )

    return main(
        style(
            """
            body { margin: 0; background: #eef2f5; color: #1f2328; font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
            main { height: 100vh; box-sizing: border-box; padding: 14px; }
            form { height: 100%; margin: 0; display: grid; grid-template-rows: auto auto 1fr auto; gap: 10px; }
            .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
            h1 { margin: 0; font-size: 20px; }
            h2 { margin: 12px 0 6px; font-size: 11px; letter-spacing: .04em; text-transform: uppercase; color: #64717c; }
            h2:first-child { margin-top: 0; }
            p { margin: 4px 0 0; color: #53606b; max-width: 640px; }
            .actions { display: flex; gap: 8px; }
            .inputs { display: flex; gap: 12px; flex-wrap: wrap; align-items: end; }
            .field { display: grid; gap: 3px; font-size: 11px; color: #64717c; text-transform: uppercase; letter-spacing: .03em; }
            .field.grow { flex: 1; min-width: 280px; }
            .field input { text-transform: none; height: 30px; padding: 0 8px; border: 1px solid #c7d0da; border-radius: 6px; background: #fff; color: #1f2328; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
            select, button { height: 30px; margin: 0; font-size: 13px; background: #fff; color: #1f2328; }
            .panes { min-height: 0; display: grid; grid-template-columns: 1.1fr 1fr; gap: 12px; }
            .pane { min-height: 0; overflow: auto; padding: 14px; border: 1px solid #c7d0da; border-radius: 6px; background: #fff; }
            .chips { display: flex; flex-wrap: wrap; gap: 5px; }
            .chips.dim { opacity: .55; }
            .chip { border-radius: 999px; padding: 3px 9px; font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
            .chip.yes { background: #d7f0dd; color: #1a7f37; }
            .chip.no { background: #eef1f4; color: #656d76; }
            .empty { color: #a0a8b0; font-size: 12px; }
            .out { margin: 0; white-space: pre; font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; color: #1f2328; }
            .status { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-height: 22px; color: #53606b; }
            .status code { background: #e0ebdf; color: #245235; border-radius: 999px; padding: 3px 8px; font-size: 12px; }
            .notes { margin-right: auto; }
            """
        ),
        on(
            on(
                on(
                    on(workbench, Event.SUBMIT, run),
                    Event.INPUT,
                    run,
                ),
                Event.CHANGE,
                run,
            ),
            Event.CLICK,
            dispatch_click,
        ),
    )


if __name__ == "__main__":
    app.run()
