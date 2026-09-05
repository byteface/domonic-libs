from collections import Counter
from pathlib import Path

import myjs
from domonic_libs.pyjs import transpile

# ---------------------------------------------------------------------------
# Real-Time Fluid Dynamics & Particle Advection -- Written in Pure Python
# ---------------------------------------------------------------------------
FLUID_PY = r'''
import math
import random

W = 600
H = 400
N = 40  # Grid resolution (40x40 simulation cells)
SIZE = (N + 2) * (N + 2)

stage = document.getElementById("stage")
ctx = stage.getContext("2d")

# Fluid Grid Buffers
u = [0.0] * SIZE        # Horizontal velocity
v = [0.0] * SIZE        # Vertical velocity
u_prev = [0.0] * SIZE
v_prev = [0.0] * SIZE
density = [0.0] * SIZE  # Smoke density
dens_prev = [0.0] * SIZE

# Indexing helper for 2D grid flattened into 1D array
def IX(i, j):
    return i + (N + 2) * j

# Tracer Particles
particles = []
for _ in range(300):
    particles.append({
        "x": random.uniform(50, W - 50),
        "y": random.uniform(50, H - 50),
        "vx": 0.0,
        "vy": 0.0,
        "hue": random.randint(180, 280)
    })

state = {"frame": 0}

# Solver: Diffusion
def diffuse(b, x, x0, diff, dt):
    a = dt * diff * N * N
    for _ in range(4):  # Gauss-Seidel iterations
        for i in range(1, N + 1):
            for j in range(1, N + 1):
                x[IX(i, j)] = (x0[IX(i, j)] + a * (
                    x[IX(i - 1, j)] + x[IX(i + 1, j)] +
                    x[IX(i, j - 1)] + x[IX(i, j + 1)]
                )) / (1 + 4 * a)

# Solver: Advection
def advect(b, d, d0, u_vel, v_vel, dt):
    dt0 = dt * N
    for i in range(1, N + 1):
        for j in range(1, N + 1):
            x_pos = i - dt0 * u_vel[IX(i, j)]
            y_pos = j - dt0 * v_vel[IX(i, j)]

            x_pos = math.max(0.5, math.min(N + 0.5, x_pos))
            y_pos = math.max(0.5, math.min(N + 0.5, y_pos))

            i0 = int(x_pos)
            i1 = i0 + 1
            j0 = int(y_pos)
            j1 = j0 + 1

            s1 = x_pos - i0
            s0 = 1.0 - s1
            t1 = y_pos - j0
            t0 = 1.0 - t1

            d[IX(i, j)] = s0 * (t0 * d0[IX(i0, j0)] + t1 * d0[IX(i0, j1)]) + \
                          s1 * (t0 * d0[IX(i1, j0)] + t1 * d0[IX(i1, j1)])

# Solver: Pressure Projection (Enforces Incompressibility)
def project(u_vel, v_vel, p, div):
    h = 1.0 / N
    for i in range(1, N + 1):
        for j in range(1, N + 1):
            div[IX(i, j)] = -0.5 * h * (
                u_vel[IX(i + 1, j)] - u_vel[IX(i - 1, j)] +
                v_vel[IX(i, j + 1)] - v_vel[IX(i, j - 1)]
            )
            p[IX(i, j)] = 0.0

    for _ in range(4):
        for i in range(1, N + 1):
            for j in range(1, N + 1):
                p[IX(i, j)] = (div[IX(i, j)] + p[IX(i - 1, j)] + p[IX(i + 1, j)] +
                               p[IX(i, j - 1)] + p[IX(i, j + 1)]) / 4.0

    for i in range(1, N + 1):
        for j in range(1, N + 1):
            u_vel[IX(i, j)] = u_vel[IX(i, j)] - 0.5 * (p[IX(i + 1, j)] - p[IX(i - 1, j)]) / h
            v_vel[IX(i, j)] = v_vel[IX(i, j)] - 0.5 * (p[IX(i, j + 1)] - p[IX(i, j - 1)]) / h

def frame(ts):
    state["frame"] = state["frame"] + 1
    f = state["frame"]

    dt = 0.1
    cell_w = W / N
    cell_h = H / N

    # Inject continuous vortex jet at center
    cx, cy = int(N / 2), int(N / 2)
    angle = f * 0.15
    u[IX(cx, cy)] = math.cos(angle) * 8.0
    v[IX(cx, cy)] = math.sin(angle) * 8.0
    density[IX(cx, cy)] = 10.0

    # Step Fluid Solver
    diffuse(1, u_prev, u, 0.0001, dt)
    diffuse(2, v_prev, v, 0.0001, dt)
    project(u_prev, v_prev, u, v)

    advect(1, u, u_prev, u_prev, v_prev, dt)
    advect(2, v, v_prev, u_prev, v_prev, dt)
    project(u, v, u_prev, v_prev)

    diffuse(0, dens_prev, density, 0.0001, dt)
    advect(0, density, dens_prev, u, v, dt)

    # Render Screen
    ctx.fillStyle = "rgba(4, 6, 12, 0.25)"  # Fluid motion blur
    ctx.fillRect(0, 0, W, H)

    # Advect and Render Tracer Particles
    for p in particles:
        # Map particle position to grid cell
        gi = int(p["x"] / cell_w)
        gj = int(p["y"] / cell_h)

        if 1 <= gi <= N and 1 <= gj <= N:
            p["vx"] = p["vx"] * 0.8 + u[IX(gi, gj)] * cell_w * 0.2
            p["vy"] = p["vy"] * 0.8 + v[IX(gi, gj)] * cell_h * 0.2

        p["x"] = p["x"] + p["vx"]
        p["y"] = p["y"] + p["vy"]

        # Screen Wrap
        if p["x"] < 0: p["x"] = W
        if p["x"] > W: p["x"] = 0
        if p["y"] < 0: p["y"] = H
        if p["y"] > H: p["y"] = 0

        # Draw Fluid Flow Particle
        speed = math.sqrt(p["vx"] * p["vx"] + p["vy"] * p["vy"])
        ctx.beginPath()
        ctx.arc(p["x"], p["y"], math.max(1.5, speed * 1.2), 0, math.pi * 2)
        ctx.fillStyle = f"hsla({int(p['hue'] + speed * 20)}, 95%, 65%, 0.8)"
        ctx.fill()

    window.requestAnimationFrame(frame)

window.requestAnimationFrame(frame)
'''

# 1. Transpile Fluid Dynamics Solver to JS
fluid_js = transpile(FLUID_PY, minify=True)

# 2. Build HTML Page
HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Navier-Stokes Fluid Dynamics (Python Source)</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #04060c; font-family: monospace; color: #70a0ff; }}
  canvas {{ display: block; border-radius: 12px; box-shadow: 0 0 60px rgba(112,160,255,0.2); }}
</style>
</head>
<body>
  <div>
    <canvas id="stage" width="600" height="400"></canvas>
  </div>
  <script>{fluid_js}</script>
</body>
</html>
"""

out = Path(__file__).with_name("pyjs_fluid.html")
out.write_text(HTML, encoding="utf-8")
print(f"Wrote {out} ({len(HTML)} bytes)")
