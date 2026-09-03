import math
from domonic.dom import document
from domonic.html import div, h1, input, label, main, option, select, style
from domonic_libs import App, preact
from domonic_libs.preact import h

app = App("Python Generative Geometry", width=1280, height=800)
container = document.createElement("div")

state = {"shape": "rose", "petals": 5}

def generate_points(shape: str, k: int, num_points: int = 360) -> str:
    """Calculates generative vector geometry in pure Python math."""
    pts = []
    cx, cy, r = 200, 200, 150
    for i in range(num_points):
        theta = (i / num_points) * 2 * math.pi * (k if shape == "star" else 1)
        if shape == "rose":
            radius = r * math.cos(k * theta)
        elif shape == "star":
            radius = r * (0.35 if i % 2 == 0 else 1.0)
        else:  # Spirograph / Hypotrochoid
            radius = r * (0.6 + 0.4 * math.sin(k * theta))
        
        x = cx + radius * math.cos(theta)
        y = cy + radius * math.sin(theta)
        pts.append(f"{x:.1f},{y:.1f}")
    return " ".join(pts)

def render_ui():
    s = state
    points_str = generate_points(s["shape"], s["petals"])
    
    # Passing 'svg' and 'polygon' as string names bypasses module import path errors
    ui = h("div", {"style": "display: flex; gap: 30px; align-items: center; padding: 40px; background: #090d16; min-height: 100vh;"},
        h("svg", {"width": "400", "height": "400", "style": "background: #0f172a; border-radius: 16px; border: 1px solid #1e293b;"},
            h("polygon", {"points": points_str, "fill": "#38bdf822", "stroke": "#38bdf8", "stroke-width": "2"})
        ),
        h("div", {"style": "display: flex; flex-direction: column; gap: 16px; font-family: system-ui; color: #f8fafc; width: 240px;"},
            h("h1", {"style": "font-size: 18px; margin: 0 0 8px; color: #38bdf8;"}, "⚡ Python Math Vector"),
            h("label", {"style": "font-size: 12px; color: #94a3b8; text-transform: uppercase;"}, "Pattern Type"),
            h("select", {"style": "padding: 8px; background: #1e293b; color: #fff; border: 1px solid #334155; border-radius: 6px;", "_onchange": on_change},
                *[h("option", {"value": opt, "selected": opt == s["shape"]}, opt.capitalize()) for opt in ["rose", "star", "spiro"]]
            ),
            h("label", {"style": "font-size: 12px; color: #94a3b8; text-transform: uppercase;"}, f"Symmetry Multiplier: {s['petals']}"),
            h("input", {"type": "range", "min": "2", "max": "12", "value": str(s["petals"]), "_oninput": on_input})
        )
    )
    preact.render(ui, container)

def on_change(e):
    state["shape"] = e.target.value
    render_ui()

def on_input(e):
    state["petals"] = int(e.target.value)
    render_ui()

render_ui()

@app.route("/")
def index():
    return main(container)

if __name__ == "__main__":
    app.run()