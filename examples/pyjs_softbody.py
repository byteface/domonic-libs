from collections import Counter
from pathlib import Path

import myjs
from domonic_libs.pyjs import transpile

# ---------------------------------------------------------------------------
# 3D Soft-Body Physics & Shadow Raytracer -- Written in Pure Python
# ---------------------------------------------------------------------------
SOFTBODY_PY = r'''
import math

W = 800
H = 500
CX = W / 2
CY = H / 2 - 30
FOCAL = 380

stage = document.getElementById("stage")
ctx = stage.getContext("2d")

# --- 3D Mass-Spring Network ---
nodes = []
# Create a 3x3x3 grid of point masses (27 nodes)
for x in range(3):
    for y in range(3):
        for z in range(3):
            nodes.append({
                "x": (x - 1) * 0.7,
                "y": (y - 1) * 0.7 - 2.5,  # Drop from air
                "z": (z - 1) * 0.7,
                "old_x": (x - 1) * 0.7,
                "old_y": (y - 1) * 0.7 - 2.5,
                "old_z": (z - 1) * 0.7
            })

# Connect neighboring nodes with elastic structural & shear springs
springs = []
rest_lengths = []

for i in range(len(nodes)):
    for j in range(i + 1, len(nodes)):
        dx = nodes[i]["x"] - nodes[j]["x"]
        dy = nodes[i]["y"] - nodes[j]["y"]
        dz = nodes[i]["z"] - nodes[j]["z"]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < 1.5:  # Connect adjacent grid nodes
            springs.append([i, j])
            rest_lengths.append(dist)

# Define 6 Outer Cube Quad Faces for 3D Rendering (indices into nodes)
faces = [
    [0, 2, 8, 6],    # Bottom
    [18, 20, 26, 24],# Top
    [0, 2, 20, 18],  # Front
    [6, 8, 26, 24],  # Back
    [0, 6, 24, 18],  # Left
    [2, 8, 26, 20]   # Right
]

state = {"frame": 0, "rot_y": 0.0}

# --- Physics Solver: Verlet Integration & Spring Forces ---
def solve_physics():
    gravity = 0.015
    damping = 0.985
    stiffness = 0.25

    # 1. Integrate Velocity (Verlet)
    for n in nodes:
        vx = (n["x"] - n["old_x"]) * damping
        vy = (n["y"] - n["old_y"]) * damping + gravity
        vz = (n["z"] - n["old_z"]) * damping

        n["old_x"] = n["x"]
        n["old_y"] = n["y"]
        n["old_z"] = n["z"]

        n["x"] = n["x"] + vx
        n["y"] = n["y"] + vy
        n["z"] = n["z"] + vz

    # 2. Relax Springs (Hooke's Law Constraint Solver)
    for _ in range(4):  # Iterative constraint satisfaction
        for idx in range(len(springs)):
            i, j = springs[idx][0], springs[idx][1]
            n1, n2 = nodes[i], nodes[j]
            rest = rest_lengths[idx]

            dx = n2["x"] - n1["x"]
            dy = n2["y"] - n1["y"]
            dz = n2["z"] - n1["z"]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)

            if dist > 0.0001:
                diff = (dist - rest) / dist * stiffness * 0.5
                n1["x"] = n1["x"] + dx * diff
                n1["y"] = n1["y"] + dy * diff
                n1["z"] = n1["z"] + dz * diff

                n2["x"] = n2["x"] - dx * diff
                n2["y"] = n2["y"] - dy * diff
                n2["z"] = n2["z"] - dz * diff

    # 3. Floor Collision & Deform Bounce
    floor_y = 1.2
    for n in nodes:
        if n["y"] > floor_y:
            n["y"] = floor_y
            # Friction on impact
            n["old_x"] = n["x"] - (n["x"] - n["old_x"]) * 0.6
            n["old_z"] = n["z"] - (n["z"] - n["old_z"]) * 0.6

def rotate_and_project(x, y, z, ry):
    # Rotate Y
    cos_a, sin_a = math.cos(ry), math.sin(ry)
    rx = x * cos_a + z * sin_a
    rz = -x * sin_a + z * cos_a

    # Camera Perspective Offset
    tz = rz + 4.5
    scale = FOCAL / tz
    px = CX + rx * scale
    py = CY + y * scale
    return px, py, tz

# Directional Shadow Ray Projection onto Floor (Y = 1.2)
def project_shadow(x, y, z, ry):
    light_dir = [0.8, -1.8, 0.5]  # Light vector
    floor_y = 1.2
    t = (floor_y - y) / light_dir[1]

    sx = x + light_dir[0] * t
    sy = floor_y
    sz = z + light_dir[2] * t
    return rotate_and_project(sx, sy, sz, ry)

def frame(ts):
    state["frame"] = state["frame"] + 1
    state["rot_y"] = state["rot_y"] + 0.012
    ry = state["rot_y"]

    solve_physics()

    # Clear Background
    ctx.fillStyle = "#070a12"
    ctx.fillRect(0, 0, W, H)

    # Render Ground Plane Grid
    ctx.strokeStyle = "rgba(45, 55, 75, 0.4)"
    ctx.lineWidth = 1
    for gz in range(-4, 5):
        p1x, p1y, _ = rotate_and_project(-3.0, 1.2, gz * 0.8, ry)
        p2x, p2y, _ = rotate_and_project(3.0, 1.2, gz * 0.8, ry)
        ctx.beginPath()
        ctx.moveTo(p1x, p1y)
        ctx.lineTo(p2x, p2y)
        ctx.stroke()

    # 1. Render Raytraced Ground Shadows
    ctx.fillStyle = "rgba(2, 4, 8, 0.65)"
    for f in faces:
        ctx.beginPath()
        for idx in range(4):
            n = nodes[f[idx]]
            spx, spy, _ = project_shadow(n["x"], n["y"], n["z"], ry)
            if idx == 0:
                ctx.moveTo(spx, spy)
            else:
                ctx.lineTo(spx, spy)
        ctx.closePath()
        ctx.fill()

    # 2. Render 3D Soft-Body Mesh (Depth Sorted / Painter's Algorithm)
    projected = []
    for f in faces:
        pts = []
        avg_z = 0.0
        for idx in range(4):
            n = nodes[f[idx]]
            px, py, pz = rotate_and_project(n["x"], n["y"], n["z"], ry)
            pts.append([px, py])
            avg_z = avg_z + pz
        avg_z = avg_z / 4.0
        projected.append({"pts": pts, "z": avg_z})

    # Sort faces back to front
    projected.sort(key=lambda a: a["z"], reverse=True)

    for item in projected:
        pts = item["pts"]
        ctx.beginPath()
        ctx.moveTo(pts[0][0], pts[0][1])
        ctx.lineTo(pts[1][0], pts[1][1])
        ctx.lineTo(pts[2][0], pts[2][1])
        ctx.lineTo(pts[3][0], pts[3][1])
        ctx.closePath()

        # Dynamic Face Shading based on Depth & Stress
        depth_color = int(math.max(80, math.min(240, 320 - item["z"] * 45)))
        ctx.fillStyle = f"rgba(88, {depth_color}, 255, 0.85)"
        ctx.fill()
        ctx.strokeStyle = "#cdd6f4"
        ctx.lineWidth = 2
        ctx.stroke()

    window.requestAnimationFrame(frame)

window.requestAnimationFrame(frame)
'''

# 1. Transpile Soft-Body Engine to JS
softbody_js = transpile(SOFTBODY_PY, minify=True)

# 2. Build HTML Page
HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>3D Soft-Body Physics & Ray-Traced Shadows (Python Source)</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #070a12; font-family: monospace; color: #89b4fa; }}
  canvas {{ display: block; border-radius: 12px; box-shadow: 0 0 60px rgba(137,180,250,0.18); }}
</style>
</head>
<body>
  <div>
    <canvas id="stage" width="800" height="500"></canvas>
  </div>
  <script>{softbody_js}</script>
</body>
</html>
"""

out = Path(__file__).with_name("pyjs_softbody.html")
out.write_text(HTML, encoding="utf-8")
print(f"Wrote {out} ({len(HTML)} bytes)")

# 3. Headless Verification via myjs
page = myjs.Page.load(str(out))
