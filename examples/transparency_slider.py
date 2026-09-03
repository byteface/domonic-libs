from domonic.events import Event
from domonic.html import button, div, h1, input, label, main, output, p, section, span, style

from domonic_libs import App, on


app = App(
    "Transparency Slider",
    width=520,
    height=360,
    debug=False,
    transparent=True,
    background_color="#000000",
    frameless=False,
    vibrancy=True,
    text_select=True,
)

state = {
    "alpha": 72,
    "accent": "teal",
}


def update_alpha(event):
    try:
        value = int(event.value)
    except (TypeError, ValueError):
        value = state["alpha"]

    value = max(10, min(100, value))
    state["alpha"] = value


def choose_accent(name):
    def handler(event):
        state["accent"] = name

    return handler


def accent_button(name, color):
    classes = ["swatch"]

    if state["accent"] == name:
        classes.append("selected")

    return on(
        button(
            span(name.title(), _class="visually-hidden"),
            _type="button",
            _class=" ".join(classes),
            _style=f"--swatch:{color}",
        ),
        Event.CLICK,
        choose_accent(name),
    )


@app.route("/")
def index():
    accent = {
        "teal": "#0f766e",
        "blue": "#2563eb",
        "rose": "#be123c",
        "lime": "#4d7c0f",
    }[state["accent"]]

    return main(
        style(
            f"""
            :root {{
                color-scheme: light;
                --panel-alpha: {state["alpha"] / 100};
                --accent: {accent};
            }}

            html,
            body {{
                margin: 0;
                padding: 0;
                background: transparent;
                color: #17202a;
            }}

            main {{
                min-height: 100vh;
                display: grid;
                place-items: center;
                padding: 20px;
                box-sizing: border-box;
                background:
                    radial-gradient(circle at 18% 16%, rgba(255,255,255,0.38), transparent 28%),
                    radial-gradient(circle at 82% 76%, rgba(255,255,255,0.22), transparent 30%);
            }}

            section {{
                width: min(100%, 440px);
                border: 1px solid rgba(255, 255, 255, 0.68);
                border-radius: 8px;
                background: rgba(255, 255, 255, var(--panel-alpha));
                box-shadow: 0 24px 70px rgba(15, 23, 42, 0.24);
                backdrop-filter: blur(18px) saturate(1.2);
                -webkit-backdrop-filter: blur(18px) saturate(1.2);
                overflow: hidden;
            }}

            h1 {{
                margin: 0 0 4px;
                font-size: 18px;
            }}

            .controls {{
                display: grid;
                gap: 18px;
                padding: 22px;
            }}

            label {{
                display: grid;
                gap: 10px;
                font-weight: 700;
            }}

            .row {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
            }}

            output {{
                min-width: 48px;
                color: var(--accent);
                text-align: right;
                font-variant-numeric: tabular-nums;
            }}

            input[type="range"] {{
                width: 100%;
                accent-color: var(--accent);
            }}

            .swatches {{
                display: flex;
                gap: 10px;
            }}

            .swatch {{
                width: 34px;
                height: 34px;
                border: 2px solid transparent;
                border-radius: 50%;
                background: var(--swatch);
                cursor: pointer;
                padding: 0;
            }}

            .swatch.selected {{
                border-color: #111827;
                box-shadow: 0 0 0 3px rgba(255,255,255,0.7);
            }}

            p {{
                margin: 0;
                color: #4b5563;
                line-height: 1.45;
            }}

            .visually-hidden {{
                position: absolute;
                width: 1px;
                height: 1px;
                overflow: hidden;
                clip: rect(0, 0, 0, 0);
            }}
            """
        ),
        section(
            div(
                h1("Transparency"),
                label(
                    div(
                        span("Panel opacity"),
                        output(f"{state['alpha']}%", _id="alpha-output"),
                        _class="row",
                    ),
                    on(
                        input(
                            _type="range",
                            _min="10",
                            _max="100",
                            _step="1",
                            _value=str(state["alpha"]),
                        ),
                        Event.INPUT,
                        update_alpha,
                    ),
                ),
                div(
                    p("Accent"),
                    div(
                        accent_button("teal", "#0f766e"),
                        accent_button("blue", "#2563eb"),
                        accent_button("rose", "#be123c"),
                        accent_button("lime", "#4d7c0f"),
                        _class="swatches",
                    ),
                    _class="row",
                ),
                p("The window is transparent. The slider changes the rendered panel opacity."),
                _class="controls",
            ),
        ),
    )


if __name__ == "__main__":
    app.run()
