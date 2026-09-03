from datetime import datetime

from domonic.events import Event
from domonic.html import button, div, h1, main, p, section, span, style

from domonic_libs import App


app = App("Clock", width=520, height=360, debug=False)

state = {
    "now": datetime.now(),
    "paused": False,
    "twenty_four_hour": True,
    "last_event": "timer",
}


def tick():
    if state["paused"]:
        return False

    state["now"] = datetime.now()


def toggle_pause(event):
    state["paused"] = not state["paused"]
    state["last_event"] = event.type


def toggle_format(event):
    state["twenty_four_hour"] = not state["twenty_four_hour"]
    state["last_event"] = event.type


def listen(node, event_type, callback):
    node.addEventListener(event_type, callback)
    return node


def clock_text():
    if state["twenty_four_hour"]:
        return state["now"].strftime("%H:%M:%S")

    return state["now"].strftime("%I:%M:%S %p").lstrip("0")


app.every(1, tick)


@app.route("/")
def index():
    pause_label = "Resume" if state["paused"] else "Pause"
    format_label = "Use 12-hour" if state["twenty_four_hour"] else "Use 24-hour"

    pause_button = listen(
        button(pause_label, _type="button", _class="primary"),
        Event.CLICK,
        toggle_pause,
    )
    format_button = listen(
        button(format_label, _type="button"),
        Event.CLICK,
        toggle_format,
    )

    return main(
        style(
            """
            body {
                margin: 0;
                padding: 0;
                background: #f4f1ea;
                color: #1f2328;
            }

            main {
                min-height: 100vh;
                display: grid;
                place-items: center;
                padding: 28px;
                box-sizing: border-box;
            }

            section {
                width: min(100%, 420px);
                border: 1px solid #d6d0c4;
                border-radius: 8px;
                background: #fffdf8;
                padding: 28px;
                box-shadow: 0 16px 42px rgba(31, 35, 40, 0.08);
            }

            h1 {
                margin: 0 0 18px;
                font-size: 18px;
                font-weight: 700;
            }

            .time {
                display: block;
                min-height: 74px;
                font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                font-size: 52px;
                line-height: 1;
                letter-spacing: 0;
                white-space: nowrap;
            }

            .date {
                margin: 8px 0 24px;
                color: #5f6b72;
            }

            .actions {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
            }

            button {
                min-height: 42px;
                border: 1px solid #b9b1a5;
                border-radius: 6px;
                background: #ffffff;
                color: inherit;
                cursor: pointer;
                font: inherit;
                font-weight: 700;
            }

            button.primary {
                background: #22577a;
                border-color: #22577a;
                color: white;
            }

            .status {
                display: flex;
                justify-content: space-between;
                gap: 16px;
                margin-top: 18px;
                color: #5f6b72;
                font-size: 13px;
            }

            @media (max-width: 430px) {
                section {
                    padding: 22px;
                }

                .time {
                    font-size: 40px;
                }

                .actions,
                .status {
                    display: grid;
                    grid-template-columns: 1fr;
                }
            }
            """
        ),
        section(
            h1("Digital clock"),
            span(clock_text(), _class="time"),
            p(state["now"].strftime("%A, %d %B %Y"), _class="date"),
            div(pause_button, format_button, _class="actions"),
            div(
                span("paused" if state["paused"] else "running"),
                span(f"last event: {state['last_event']}"),
                _class="status",
            ),
        ),
    )


app.run()
