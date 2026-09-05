from collections import Counter
from pathlib import Path

import myjs
from domonic_libs.pyjs import transpile

# ---------------------------------------------------------------------------
# 3D Raymarched SDF Scene -- Written in Pure Python
# ---------------------------------------------------------------------------
RAYMARCH_PY = r'''
import math

W = 200
H = 150
stage = document.getElementById("stage")
ctx = stage.getContext("2d")

# Create offscreen buffer for raw pixel manipulation
img = ctx.createImageData(W, H)
data = img.data

state = {"frame": 0}

# --- Signed Distance Functions (SDFs) ---
def sd_sphere(px, py, pz, r):
    return math.sqrt(px * px + py * py + pz * pz) - r

def sd_box(px, py, pz, bx, by, bz):
    dx = math.max(0.0, math.abs(px) - bx)
    dy = math.max(0.0, math.abs(py) - by)
    dz = math.max(0.0, math.abs(pz) - bz)
    return math.sqrt(dx * dx + dy * dy + dz * dz)

def map_scene(px, py, pz, t):
    # Rotating sphere subtracted from/blended with floating cube
    rad = t * 0.8
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    rx = px * cos_a - pz * sin_a
    rz = px * sin_a + pz * cos_a

    box_dist = sd_box(rx, py, rz, 1.0, 1.0, 1.0)
    sphere_dist = sd_sphere(px - math.sin(t) * 1.2, py, pz, 1.1)

    # Smooth CSG Union
    k = 0.5
    h = math.max(0.0, math.min(1.0, 0.5 + 0.5 * (sphere_dist - box_dist) / k))
    return (box_dist * h + sphere_dist * (1.0 - h)) - k * h * (1.0 - h)

# Calculate Surface Normal
def calc_normal(px, py, pz, t):
    e = 0.01
    nx = map_scene(px + e, py, pz, t) - map_scene(px - e, py, pz, t)
    ny = map_scene(px, py + e, pz, t) - map_scene(px, py - e, pz, t)
    nz = map_scene(px, py, pz + e, t) - map_scene(px, py, pz - e, t)
    len_n = math.sqrt(nx * nx + ny * ny + nz * nz)
    if len_n == 0:
        return 0.0, 0.0, 0.0
    return nx / len_n, ny / len_n, nz / len_n

def frame(ts):
    state["frame"] = state["frame"] + 1
    t = state["frame"] * 0.05

    # Light Position
    lx, ly, lz = 2.0, 3.0, -3.0

    idx = 0
    # Raymarch Loop per pixel
    for y in range(H):
        py = (y - H / 2.0) / (H / 2.0)
        for x in range(W):
            px = (x - W / 2.0) / (H / 2.0)

            # Ray Direction
            rd_x, rd_y, rd_z = px, py, 1.0
            rd_len = math.sqrt(rd_x * rd_x + rd_y * rd_y + rd_z * rd_z)
            rd_x, rd_y, rd_z = rd_x / rd_len, rd_y / rd_len, rd_z / rd_len

            # March Ray from Camera Origin
            ro_x, ro_y, ro_z = 0.0, 0.0, -3.5
            dist_traveled = 0.0
            hit = False

            for step in range(24):
                cx = ro_x + rd_x * dist_traveled
                cy = ro_y + rd_y * dist_traveled
                cz = ro_z + rd_z * dist_traveled

                d = map_scene(cx, cy, cz, t)
                if d < 0.02:
                    hit = True
                    break
                dist_traveled = dist_traveled + d
                if dist_traveled > 8.0:
                    break

            if hit:
                hx = ro_x + rd_x * dist_traveled
                hy = ro_y + rd_y * dist_traveled
                hz = ro_z + rd_z * dist_traveled

                # Lighting & Shading
                nx, ny, nz = calc_normal(hx, hy, hz, t)
                ld_x, ld_y, ld_z = lx - hx, ly - hy, lz - hz
                ld_len = math.sqrt(ld_x * ld_x + ld_y * ld_y + ld_z * ld_z)
                diffuse = math.max(0.1, (nx * (ld_x / ld_len) + ny * (ld_y / ld_len) + nz * (ld_z / ld_len)))

                # Distance Fog
                fog = math.max(0.0, 1.0 - dist_traveled / 8.0)

                data[idx] = int(diffuse * fog * 180 + 20)
                data[idx + 1] = int(diffuse * fog * 240 + 30)
                data[idx + 2] = int(diffuse * fog * 255 + 50)
                data[idx + 3] = 255
            else:
                # Background Gradient
                data[idx] = 10
                data[idx + 1] = 15
                data[idx + 2] = 25
                data[idx + 3] = 255

            idx = idx + 4

    ctx.putImageData(img, 0, 0)
    window.requestAnimationFrame(frame)

window.requestAnimationFrame(frame)
'''

# 1. Transpile Python 3D Raymarcher to JS
raymarch_js = transpile(RAYMARCH_PY, minify=True)

# 2. Build Standalone HTML Page
HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Pure Python 3D SDF Raymarcher</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #050811; font-family: monospace; color: #79c0ff; }}
  canvas {{ display: block; border-radius: 12px; width: 600px; height: 450px;
            image-rendering: pixelated; box-shadow: 0 0 50px rgba(121,192,255,0.2); }}
</style>
</head>
<body>
  <div>
    <canvas id="stage" width="200" height="150"></canvas>
  </div>
  <script>{raymarch_js}</script>
</body>
</html>
"""

out = Path(__file__).with_name("pyjs_raymarch.html")
out.write_text(HTML, encoding="utf-8")
print(f"Wrote {out} ({len(HTML)} bytes)")

# 3. Headless Verification via myjs
page = myjs.Page.load(str(out))
# assert not page.errors, page.errors

# ctx = page.query("#stage").getContext("2d")

# print("\n--- Headless 3D Raymarcher Verification ---")
# for step in range(1, 4):
#     page.frames(5)
    
#     # Calculate bytes processed per frame directly from JS runtime state
#     frame_no = page.eval("state.frame")
#     px_count = page.eval("W * H")
#     byte_writes = page.eval("data.length")
    
#     print(f"Step {step} (Frame {frame_no}):")
#     print(f"  Raymarched Pixels : {px_count} ({W}x{H} resolution)")
#     print(f"  RGBA Byte Writes  : {byte_writes} bytes blitted via putImageData")

# print("\nDone! Open pyjs_raymarch.html in a browser to see the real-time 3D raymarched sphere morphing.")