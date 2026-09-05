from collections import Counter
from pathlib import Path

import myjs
from domonic_libs.pyjs import transpile

# ---------------------------------------------------------------------------
# 3D Wireframe Cube with Rotation & Lighting -- Written in Pure Python
# ---------------------------------------------------------------------------
CUBE_PY = r'''
import math

W = 600
H = 600
CX = W / 2
CY = H / 2
FOCAL_LENGTH = 300

stage = document.getElementById("stage")
ctx = stage.getContext("2d")

# 3D Vertices of a unit cube
nodes = [
    [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
    [-1, -1,  1], [1, -1,  1], [1, 1,  1], [-1, 1,  1]
]

# 12 Edges connecting the 8 vertices
edges = [
    [0, 1], [1, 2], [2, 3], [3, 0],  # Back face
    [4, 5], [5, 6], [6, 7], [7, 4],  # Front face
    [0, 4], [1, 5], [2, 6], [3, 7]   # Connecting edges
]

state = {"rx": 0.0, "ry": 0.0, "rz": 0.0}

def rotate_and_project(x, y, z, rx, ry, rz):
    # Rotate around X-axis
    rad = rx
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    y1 = y * cos_a - z * sin_a
    z1 = y * sin_a + z * cos_a

    # Rotate around Y-axis
    rad = ry
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    x2 = x * cos_a + z1 * sin_a
    z2 = -x * sin_a + z1 * cos_a

    # Rotate around Z-axis
    rad = rz
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    x3 = x2 * cos_a - y1 * sin_a
    y3 = x2 * sin_a + y1 * cos_a

    # Perspective Projection (Shift Z back by 3.5 units to prevent div by zero)
    z_offset = z2 + 3.5
    scale = FOCAL_LENGTH / z_offset
    
    px = CX + x3 * scale
    py = CY + y3 * scale
    return px, py, z_offset

def frame(ts):
    state["rx"] = state["rx"] + 0.02
    state["ry"] = state["ry"] + 0.03
    state["rz"] = state["rz"] + 0.01

    # Clear screen
    ctx.fillStyle = "#0a0c10"
    ctx.fillRect(0, 0, W, H)

    # Transform all vertices
    projected = []
    for node in nodes:
        px, py, pz = rotate_and_project(
            node[0], node[1], node[2], 
            state["rx"], state["ry"], state["rz"]
        )
        projected.append([px, py, pz])

    # Draw wireframe edges with dynamic depth color
    ctx.lineWidth = 3
    for edge in edges:
        p1 = projected[edge[0]]
        p2 = projected[edge[1]]
        
        # Calculate average depth for lighting effect
        avg_z = (p1[2] + p2[2]) / 2.0
        brightness = int(math.pow(1.0 / (avg_z * 0.35), 1.5) * 255)
        
        ctx.strokeStyle = f"rgb(0, {min(255, brightness)}, {min(255, brightness + 50)})"
        ctx.beginPath()
        ctx.moveTo(p1[0], p1[1])
        ctx.lineTo(p2[0], p2[1])
        ctx.stroke()

    window.requestAnimationFrame(frame)

window.requestAnimationFrame(frame)
'''

# 1. Transpile Python logic to JavaScript
cube_js = transpile(CUBE_PY, minify=True)

# 2. Build standalone HTML file
HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>3D Cube in Python</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #020305; font-family: monospace; color: #89b4fa; }}
  canvas {{ display: block; border-radius: 12px; box-shadow: 0 0 40px rgba(0,255,200,0.15); }}
</style>
</head>
<body>
  <div>
    <canvas id="stage" width="600" height="600"></canvas>
  </div>
  <script>{cube_js}</script>
</body>
</html>
"""

out = Path(__file__).with_name("pyjs_cube.html")
out.write_text(HTML, encoding="utf-8")
print(f"Wrote {out} ({len(HTML)} bytes)")

# 3. Drive the page headlessly with myjs
page = myjs.Page.load(str(out))
assert not page.errors, page.errors

ctx = page.query("#stage").getContext("2d")

print("\n--- Headless Verification ---")
for f in range(1, 4):
    page.frames(10)
    commands = Counter(c["name"] for c in ctx.commands)
    print(f"Frame {f * 10}: Rendered {commands['lineTo']} edge lines and {commands['stroke']} strokes")
    ctx.commands.clear()

print("\nDone! Open pyjs_cube.html in your browser to see the 3D cube spinning.")