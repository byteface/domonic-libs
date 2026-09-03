from decimal import Decimal, InvalidOperation

from domonic.events import Event
from domonic.html import button, div, h1, main, section, span, style

from domonic_libs import App


app = App("Calculator", width=380, height=560, debug=False)

state = {
    "display": "0",
    "stored": None,
    "operator": None,
    "waiting": False,
    "expression": "",
}


def listen(node, event_type, callback):
    node.addEventListener(event_type, callback)
    return node


def decimal_text(value):
    text = format(value, "f")

    if "." in text:
        text = text.rstrip("0").rstrip(".")

    return text or "0"


def current_value():
    try:
        return Decimal(state["display"])
    except InvalidOperation:
        return Decimal("0")


def input_digit(digit):
    def handler(event):
        if state["waiting"] or state["display"] == "0":
            state["display"] = digit
        else:
            state["display"] += digit

        state["waiting"] = False

    return handler


def input_decimal(event):
    if state["waiting"]:
        state["display"] = "0."
        state["waiting"] = False
        return

    if "." not in state["display"]:
        state["display"] += "."


def clear(event):
    state.update(
        {
            "display": "0",
            "stored": None,
            "operator": None,
            "waiting": False,
            "expression": "",
        }
    )


def toggle_sign(event):
    if state["display"] == "0":
        return

    if state["display"].startswith("-"):
        state["display"] = state["display"][1:]
    else:
        state["display"] = f"-{state['display']}"


def percent(event):
    state["display"] = decimal_text(current_value() / Decimal("100"))


def choose_operator(operator):
    def handler(event):
        value = current_value()

        if state["operator"] and not state["waiting"]:
            value = calculate()
            state["display"] = decimal_text(value)

        state["stored"] = value
        state["operator"] = operator
        state["waiting"] = True
        state["expression"] = f"{decimal_text(value)} {operator}"

    return handler


def calculate():
    left = state["stored"]
    right = current_value()
    operator = state["operator"]

    if left is None or operator is None:
        return right

    if operator == "+":
        return left + right
    if operator == "-":
        return left - right
    if operator == "x":
        return left * right
    if operator == "/":
        if right == 0:
            raise ZeroDivisionError
        return left / right

    return right


def equals(event):
    try:
        result = calculate()
    except ZeroDivisionError:
        state.update(
            {
                "display": "Error",
                "stored": None,
                "operator": None,
                "waiting": True,
                "expression": "Cannot divide by zero",
            }
        )
        return

    state["expression"] = ""

    if state["operator"] is not None and state["stored"] is not None:
        state["expression"] = (
            f"{decimal_text(state['stored'])} "
            f"{state['operator']} {state['display']} ="
        )

    state["display"] = decimal_text(result)
    state["stored"] = None
    state["operator"] = None
    state["waiting"] = True


def calc_button(label, callback, class_name=""):
    attrs = {"_type": "button"}

    if class_name:
        attrs["_class"] = class_name

    return listen(button(label, **attrs), Event.CLICK, callback)


@app.route("/")
def index():
    keys = (
        ("C", clear, "utility"),
        ("+/-", toggle_sign, "utility"),
        ("%", percent, "utility"),
        ("/", choose_operator("/"), "operator"),
        ("7", input_digit("7"), ""),
        ("8", input_digit("8"), ""),
        ("9", input_digit("9"), ""),
        ("x", choose_operator("x"), "operator"),
        ("4", input_digit("4"), ""),
        ("5", input_digit("5"), ""),
        ("6", input_digit("6"), ""),
        ("-", choose_operator("-"), "operator"),
        ("1", input_digit("1"), ""),
        ("2", input_digit("2"), ""),
        ("3", input_digit("3"), ""),
        ("+", choose_operator("+"), "operator"),
        ("0", input_digit("0"), "zero"),
        (".", input_decimal, ""),
        ("=", equals, "operator"),
    )

    return main(
        style(
            """
            body {
                margin: 0;
                padding: 0;
                background: #edf1f5;
                color: #1f2328;
            }

            main {
                min-height: 100vh;
                display: grid;
                place-items: center;
                padding: 22px;
                box-sizing: border-box;
            }

            section {
                width: min(100%, 320px);
                border: 1px solid #cbd3dc;
                border-radius: 8px;
                background: #ffffff;
                padding: 16px;
                box-shadow: 0 16px 42px rgba(31, 35, 40, 0.12);
            }

            h1 {
                margin: 0 0 14px;
                font-size: 16px;
            }

            .screen {
                display: grid;
                align-content: end;
                gap: 6px;
                min-height: 104px;
                margin-bottom: 12px;
                border-radius: 8px;
                background: #202833;
                color: white;
                padding: 16px;
                box-sizing: border-box;
                text-align: right;
            }

            .expression {
                min-height: 19px;
                color: #aeb8c4;
                font-size: 13px;
            }

            .display {
                overflow: hidden;
                font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                font-size: 38px;
                line-height: 1.1;
                letter-spacing: 0;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .keys {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 8px;
            }

            button {
                aspect-ratio: 1;
                border: 1px solid #cbd3dc;
                border-radius: 8px;
                background: #f8fafc;
                color: inherit;
                cursor: pointer;
                font: inherit;
                font-size: 20px;
                font-weight: 700;
            }

            button.utility {
                background: #e7edf3;
            }

            button.operator {
                background: #22577a;
                border-color: #22577a;
                color: white;
            }

            button.zero {
                grid-column: span 2;
                aspect-ratio: auto;
            }

            button:active {
                transform: translateY(1px);
            }
            """
        ),
        section(
            h1("Calculator"),
            div(
                span(state["expression"], _class="expression"),
                span(state["display"], _class="display"),
                _class="screen",
            ),
            div(
                *[
                    calc_button(label, callback, class_name)
                    for label, callback, class_name in keys
                ],
                _class="keys",
            ),
        ),
    )


app.run()
