from pathlib import Path

from domonic.events import Event, PointerEvent
from domonic.geom.vec2 import vec2
from domonic.html import button, div, h1, main, p, section, span, style
from domonic.svg import circle, line, rect, svg

from domonic_libs import App


WIDTH = 800
HEIGHT = 500

app = App("SVG Sketchbook", width=980, height=700, debug=False)

state = {
    "tool": "rect",
    "stroke": "#22577a",
    "fill": "#ffffff",
    "anchor": None,
    "shapes": [],
    "status": "Choose a tool, then click two points on the canvas.",
}


def listen(node, event_type, callback):
    node.addEventListener(event_type, callback)
    return node


def point_from_event(event):
    x = max(0, min(WIDTH, int(event.offsetX or 0)))
    y = max(0, min(HEIGHT, int(event.offsetY or 0)))
    return vec2(x, y)


def choose_tool(tool):
    def handler(event):
        state["tool"] = tool
        state["anchor"] = None
        state["status"] = f"{tool.title()} tool selected."

    return handler


def choose_stroke(color):
    def handler(event):
        state["stroke"] = color
        state["status"] = f"Stroke set to {color}."

    return handler


def choose_fill(color):
    def handler(event):
        state["fill"] = color
        state["status"] = f"Fill set to {color}."

    return handler


def clear_canvas(event):
    state["anchor"] = None
    state["shapes"] = []
    state["status"] = "Canvas cleared."


def undo(event):
    if state["shapes"]:
        state["shapes"].pop()
        state["status"] = "Removed last shape."
    else:
        state["status"] = "Nothing to undo."


def save_svg(event):
    path = app.save_file(
        filename="sketch.svg",
        file_types=(
            "SVG files (*.svg)",
            "All files (*.*)",
        ),
    )
    path = path[0] if isinstance(path, (list, tuple)) and path else path

    if not path:
        state["status"] = "Save canceled."
        return

    Path(path).write_text(svg_document(), encoding="utf-8")
    state["status"] = f"Saved {Path(path).name}."


def canvas_click(event):
    point = point_from_event(event)

    if state["anchor"] is None:
        state["anchor"] = point
        state["status"] = f"Anchor set at {point.x}, {point.y}."
        return

    add_shape(state["anchor"], point)
    state["anchor"] = None


def add_shape(start, end):
    tool = state["tool"]
    shape = {
        "tool": tool,
        "start": start.obj(),
        "end": end.obj(),
        "stroke": state["stroke"],
        "fill": state["fill"],
    }

    if tool == "circle":
        shape["radius"] = int(start.distance(end))

    state["shapes"].append(shape)
    state["status"] = f"Added {tool}."


def shape_node(shape):
    start = vec2(shape["start"]["x"], shape["start"]["y"])
    end = vec2(shape["end"]["x"], shape["end"]["y"])
    stroke = shape["stroke"]
    fill = shape["fill"]

    if shape["tool"] == "line":
        return line(
            _x1=start.x,
            _y1=start.y,
            _x2=end.x,
            _y2=end.y,
            _stroke=stroke,
            _stroke_width="3",
            _stroke_linecap="round",
        )

    if shape["tool"] == "circle":
        return circle(
            _cx=start.x,
            _cy=start.y,
            _r=shape["radius"],
            _fill=fill,
            _stroke=stroke,
            _stroke_width="3",
        )

    x = min(start.x, end.x)
    y = min(start.y, end.y)
    width = abs(end.x - start.x)
    height = abs(end.y - start.y)
    return rect(
        _x=x,
        _y=y,
        _width=width,
        _height=height,
        _fill=fill,
        _stroke=stroke,
        _stroke_width="3",
    )


def anchor_node():
    if state["anchor"] is None:
        return ""

    anchor = state["anchor"]
    return circle(
        _cx=anchor.x,
        _cy=anchor.y,
        _r="6",
        _fill="#c44536",
        _stroke="#ffffff",
        _stroke_width="2",
    )


def drawing():
    canvas = svg(
        rect(
            _x="0",
            _y="0",
            _width=WIDTH,
            _height=HEIGHT,
            _fill="#ffffff",
        ),
        *[shape_node(shape) for shape in state["shapes"]],
        anchor_node(),
        _class="canvas",
        _width=str(WIDTH),
        _height=str(HEIGHT),
        _viewBox=f"0 0 {WIDTH} {HEIGHT}",
    )
    return listen(canvas, PointerEvent.POINTERDOWN, canvas_click)


def svg_document():
    artwork = svg(
        *[shape_node(shape) for shape in state["shapes"]],
        _xmlns="http://www.w3.org/2000/svg",
        _width=str(WIDTH),
        _height=str(HEIGHT),
        _viewBox=f"0 0 {WIDTH} {HEIGHT}",
    )
    return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" + str(artwork)


def tool_button(label, tool):
    classes = ["tool"]

    if state["tool"] == tool:
        classes.append("active")

    return listen(
        button(label, _type="button", _class=" ".join(classes)),
        Event.CLICK,
        choose_tool(tool),
    )


def color_button(color, callback, active):
    classes = ["swatch"]

    if active:
        classes.append("active")

    return listen(
        button(
            "",
            _type="button",
            _class=" ".join(classes),
            _style=f"background: {color};",
            _title=color,
        ),
        Event.CLICK,
        callback(color),
    )


def action_button(label, callback, primary=False):
    classes = "primary" if primary else "secondary"
    return listen(
        button(label, _type="button", _class=classes),
        Event.CLICK,
        callback,
    )


app.menu(
    "File",
    app.menu_item("Save SVG...", save_svg),
)
app.menu(
    "Edit",
    app.menu_item("Undo", undo),
    app.menu_item("Clear", clear_canvas),
)


@app.route("/")
def index():
    stroke_colors = ("#22577a", "#2f855a", "#c44536", "#111827")
    fill_colors = ("#ffffff", "#e7f1f5", "#f8e9a1", "#f6c5c0")
    anchor = state["anchor"]

    return main(
        style(
            """
            :root {
                color-scheme: light;
            }

            body {
                margin: 0;
                padding: 0;
                background: #eef2f5;
                color: #1f2328;
            }

            main {
                height: 100vh;
                display: grid;
                grid-template-columns: 220px minmax(0, 1fr);
                overflow: hidden;
            }

            .sidebar {
                display: grid;
                align-content: start;
                gap: 18px;
                border-right: 1px solid #cbd3dc;
                background: #ffffff;
                padding: 18px;
                box-sizing: border-box;
            }

            h1,
            p {
                margin: 0;
            }

            h1 {
                font-size: 18px;
            }

            .group {
                display: grid;
                gap: 8px;
            }

            .label {
                color: #66727f;
                font-size: 12px;
                font-weight: 800;
                text-transform: uppercase;
            }

            .tools,
            .actions {
                display: grid;
                gap: 8px;
            }

            .swatches {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 8px;
            }

            button {
                min-height: 36px;
                border: 1px solid #bec8d2;
                border-radius: 6px;
                background: #ffffff;
                color: #1f2328;
                cursor: pointer;
                font: inherit;
                font-weight: 700;
                padding: 7px 10px;
            }

            button.active {
                border-color: #22577a;
                box-shadow: inset 0 0 0 2px rgba(34, 87, 122, 0.25);
            }

            button.primary {
                border-color: #22577a;
                background: #22577a;
                color: white;
            }

            button.secondary {
                background: #f7f9fb;
            }

            .swatch {
                aspect-ratio: 1;
                min-height: 0;
                padding: 0;
            }

            .workspace {
                min-width: 0;
                overflow: auto;
                padding: 24px;
                box-sizing: border-box;
            }

            .canvas-wrap {
                width: max-content;
                border: 1px solid #cbd3dc;
                border-radius: 8px;
                background: #ffffff;
                padding: 12px;
                box-shadow: 0 16px 42px rgba(31, 35, 40, 0.1);
            }

            .canvas {
                display: block;
                touch-action: none;
                background: white;
                cursor: crosshair;
            }

            .status {
                margin-top: 14px;
                color: #66727f;
                font-size: 13px;
            }

            @media (max-width: 780px) {
                main {
                    height: auto;
                    min-height: 100vh;
                    grid-template-columns: 1fr;
                    overflow: visible;
                }

                .sidebar {
                    border-right: 0;
                    border-bottom: 1px solid #cbd3dc;
                }
            }
            """
        ),
        section(
            h1("SVG Sketchbook"),
            div(
                span("Tools", _class="label"),
                div(
                    tool_button("Rectangle", "rect"),
                    tool_button("Circle", "circle"),
                    tool_button("Line", "line"),
                    _class="tools",
                ),
                _class="group",
            ),
            div(
                span("Stroke", _class="label"),
                div(
                    *[
                        color_button(
                            color,
                            choose_stroke,
                            state["stroke"] == color,
                        )
                        for color in stroke_colors
                    ],
                    _class="swatches",
                ),
                _class="group",
            ),
            div(
                span("Fill", _class="label"),
                div(
                    *[
                        color_button(
                            color,
                            choose_fill,
                            state["fill"] == color,
                        )
                        for color in fill_colors
                    ],
                    _class="swatches",
                ),
                _class="group",
            ),
            div(
                span("Actions", _class="label"),
                div(
                    action_button("Undo", undo),
                    action_button("Clear", clear_canvas),
                    action_button("Save SVG", save_svg, primary=True),
                    _class="actions",
                ),
                _class="group",
            ),
            p(
                f"Anchor: {anchor.x}, {anchor.y}" if anchor else "Anchor: none",
                _class="status",
            ),
            _class="sidebar",
        ),
        section(
            div(drawing(), _class="canvas-wrap"),
            p(
                f"{len(state['shapes'])} shapes. {state['status']}",
                _class="status",
            ),
            _class="workspace",
        ),
    )


app.run()
