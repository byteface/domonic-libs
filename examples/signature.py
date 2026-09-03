from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

from domonic.events import Event
from domonic.html import button, canvas, div, h1, main, p, script, section, span, style

from domonic_libs import App, on


app = App(
    "Signature",
    width=820,
    height=520,
    debug=False,
    transparent=True,
    background_color="#000000",
    text_select=True,
)

state = {
    "status": "Draw your signature, then save it as a PNG.",
    "ink": "#111827",
}


def timestamp_name():
    return f"signature-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"


def set_status(message):
    state["status"] = message

    if app.window is not None:
        app.evaluate_js(
            "var status = document.getElementById('status');"
            f"if (status) status.textContent = {message!r};"
        )


def write_png(path, data_url):
    prefix = "data:image/png;base64,"

    path = Path(path)
    if path.suffix.lower() != ".png":
        path = path.with_suffix(".png")

    if not isinstance(data_url, str) or not data_url.startswith(prefix):
        set_status("PNG export failed.")
        return

    path.write_bytes(base64.b64decode(data_url.removeprefix(prefix)))
    set_status(f"Saved {path.name}.")


def save_png(event):
    path = app.save_file(
        filename=timestamp_name(),
        file_types=(
            "PNG files (*.png)",
            "All files (*.*)",
        ),
    )
    path = path[0] if isinstance(path, (list, tuple)) and path else path

    if not path:
        set_status("Save canceled.")
        return False

    set_status("Saving PNG...")
    data_url = app.evaluate_js("window.signaturePad ? window.signaturePad.exportPNG() : ''")
    write_png(path, data_url)
    return False


def clear_signature(event):
    if app.window is not None:
        app.evaluate_js("if (window.signaturePad) window.signaturePad.clear();")

    set_status("Canvas cleared.")
    return False


def choose_ink(color):
    def handler(event):
        state["ink"] = color

        if app.window is not None:
            app.evaluate_js(
                "if (window.signaturePad) "
                f"window.signaturePad.setInk({color!r});"
            )

        return False

    return handler


def action_button(label, callback, class_name=""):
    classes = ["button"]

    if class_name:
        classes.append(class_name)

    return on(
        button(label, _type="button", _class=" ".join(classes)),
        Event.CLICK,
        callback,
    )


def ink_button(label, color):
    classes = ["ink"]

    if state["ink"] == color:
        classes.append("selected")

    return on(
        button(
            span(label, _class="visually-hidden"),
            _type="button",
            _class=" ".join(classes),
            _style=f"--ink:{color}",
        ),
        Event.CLICK,
        choose_ink(color),
    )


def pad_script():
    return """
    (function () {
        function initSignaturePad() {
            var canvas = document.getElementById("signature-pad");

            if (!canvas || canvas.dataset.ready === "true") {
                return;
            }

            var ctx = canvas.getContext("2d");
            var drawing = false;
            var ink = canvas.dataset.ink || "#111827";
            var last = null;

            function resize() {
                var rect = canvas.getBoundingClientRect();
                var ratio = window.devicePixelRatio || 1;
                var image = canvas.toDataURL("image/png");

                canvas.width = Math.max(1, Math.floor(rect.width * ratio));
                canvas.height = Math.max(1, Math.floor(rect.height * ratio));
                ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
                ctx.lineCap = "round";
                ctx.lineJoin = "round";

                if (image) {
                    var img = new Image();
                    img.onload = function () {
                        ctx.drawImage(img, 0, 0, rect.width, rect.height);
                    };
                    img.src = image;
                }
            }

            function point(event) {
                var rect = canvas.getBoundingClientRect();
                return {
                    x: event.clientX - rect.left,
                    y: event.clientY - rect.top
                };
            }

            function draw(event) {
                var current;

                if (!drawing) {
                    return;
                }

                event.preventDefault();
                current = point(event);
                ctx.strokeStyle = ink;
                ctx.lineWidth = 3.2;
                ctx.beginPath();
                ctx.moveTo(last.x, last.y);
                ctx.lineTo(current.x, current.y);
                ctx.stroke();
                last = current;
            }

            function start(event) {
                event.preventDefault();
                canvas.setPointerCapture(event.pointerId);
                drawing = true;
                last = point(event);
            }

            function stop(event) {
                if (!drawing) {
                    return;
                }

                event.preventDefault();
                drawing = false;
            }

            window.signaturePad = {
                clear: function () {
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                },
                exportPNG: function () {
                    var imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                    var data = imageData.data;
                    var minX = canvas.width;
                    var minY = canvas.height;
                    var maxX = -1;
                    var maxY = -1;
                    var padding = Math.round(18 * (window.devicePixelRatio || 1));
                    var crop;
                    var cropCtx;
                    var width;
                    var height;
                    var x;
                    var y;
                    var index;

                    for (y = 0; y < canvas.height; y += 1) {
                        for (x = 0; x < canvas.width; x += 1) {
                            index = (y * canvas.width + x) * 4 + 3;

                            if (data[index] === 0) {
                                continue;
                            }

                            minX = Math.min(minX, x);
                            minY = Math.min(minY, y);
                            maxX = Math.max(maxX, x);
                            maxY = Math.max(maxY, y);
                        }
                    }

                    if (maxX < 0 || maxY < 0) {
                        return "";
                    }

                    minX = Math.max(0, minX - padding);
                    minY = Math.max(0, minY - padding);
                    maxX = Math.min(canvas.width - 1, maxX + padding);
                    maxY = Math.min(canvas.height - 1, maxY + padding);
                    width = maxX - minX + 1;
                    height = maxY - minY + 1;

                    crop = document.createElement("canvas");
                    crop.width = width;
                    crop.height = height;
                    cropCtx = crop.getContext("2d");
                    cropCtx.putImageData(ctx.getImageData(minX, minY, width, height), 0, 0);

                    return crop.toDataURL("image/png");
                },
                setInk: function (color) {
                    ink = color;
                    canvas.dataset.ink = color;
                }
            };

            canvas.dataset.ready = "true";
            resize();
            window.addEventListener("resize", resize);
            canvas.addEventListener("pointerdown", start);
            canvas.addEventListener("pointermove", draw);
            canvas.addEventListener("pointerup", stop);
            canvas.addEventListener("pointercancel", stop);
            canvas.addEventListener("pointerleave", stop);
        }

        window.addEventListener("load", initSignaturePad);
        window.addEventListener("pywebviewready", initSignaturePad);
        setTimeout(initSignaturePad, 0);
    }());
    """


app.menu(
    "File",
    app.menu_item("Save PNG...", save_png, refresh=False),
)
app.menu(
    "Edit",
    app.menu_item("Clear", clear_signature, refresh=False),
)


@app.route("/")
def index():
    return main(
        style(
            """
            :root {
                color-scheme: light;
            }

            html,
            body {
                margin: 0;
                padding: 0;
                background: transparent;
                color: #17202a;
            }

            main {
                min-height: 100vh;
                display: grid;
                place-items: center;
                padding: 24px;
                box-sizing: border-box;
                background: rgba(245, 247, 250, 0.72);
            }

            section {
                width: min(100%, 740px);
                display: grid;
                grid-template-rows: auto minmax(220px, 1fr) auto;
                gap: 14px;
                border: 1px solid rgba(140, 149, 159, 0.72);
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.84);
                padding: 18px;
                box-sizing: border-box;
                box-shadow: 0 24px 70px rgba(31, 35, 40, 0.18);
            }

            .topbar,
            .bottombar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 14px;
            }

            h1 {
                margin: 0 0 4px;
                font-size: 20px;
            }

            p {
                margin: 0;
                color: #57606a;
            }

            canvas {
                width: 100%;
                height: 280px;
                display: block;
                border: 1px solid #8c959f;
                border-radius: 8px;
                background: #ffffff;
                touch-action: none;
                cursor: crosshair;
            }

            .actions,
            .inks {
                display: flex;
                align-items: center;
                gap: 10px;
            }

            .button {
                min-height: 38px;
                border: 1px solid #8c959f;
                border-radius: 6px;
                background: #ffffff;
                color: #24292f;
                cursor: pointer;
                font: inherit;
                padding: 0 14px;
            }

            .button.primary {
                background: #0969da;
                border-color: #0969da;
                color: #ffffff;
            }

            .ink {
                width: 30px;
                height: 30px;
                border: 2px solid transparent;
                border-radius: 50%;
                background: var(--ink);
                cursor: pointer;
                padding: 0;
            }

            .ink.selected {
                border-color: #111827;
                box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.8);
            }

            #status {
                font-size: 13px;
            }

            .visually-hidden {
                position: absolute;
                width: 1px;
                height: 1px;
                overflow: hidden;
                clip: rect(0, 0, 0, 0);
            }

            @media (max-width: 640px) {
                .topbar,
                .bottombar {
                    align-items: flex-start;
                    flex-direction: column;
                }

                canvas {
                    height: 240px;
                }
            }
            """
        ),
        section(
            div(
                div(
                    h1("Signature"),
                    p("Draw with mouse, trackpad, or stylus."),
                ),
                div(
                    action_button("Clear", clear_signature),
                    action_button("Save PNG", save_png, "primary"),
                    _class="actions",
                ),
                _class="topbar",
            ),
            canvas(_id="signature-pad", **{"_data-ink": state["ink"]}),
            div(
                div(
                    ink_button("Black", "#111827"),
                    ink_button("Blue", "#1d4ed8"),
                    ink_button("Green", "#047857"),
                    _class="inks",
                ),
                p(state["status"], _id="status"),
                _class="bottombar",
            ),
        ),
        script(pad_script()),
    )


if __name__ == "__main__":
    app.run()
