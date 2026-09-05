from collections import Counter
from pathlib import Path

import myjs
from domonic_libs.pyjs import transpile

# ---------------------------------------------------------------------------
# Interactive 3D Retro Synthwave Racer Game -- Written in Pure Python
# ---------------------------------------------------------------------------
RACER_PY = r'''
import math

W = 800
H = 500
HALF_W = W / 2
HALF_H = H / 2

stage = document.getElementById("stage")
ctx = stage.getContext("2d")

# --- Track Segment Generation ---
ROAD_WIDTH = 2000
SEGMENT_LENGTH = 200
RUMBLE_LENGTH = 3

segments = []
# Create 300 track segments with curves and elevation hills
for i in range(300):
    curve = 0.0
    height = 0.0
    
    # Add S-curves and rolling hills
    if 30 <= i <= 90:
        curve = 2.5
        height = math.sin(i * 0.1) * 1200
    elif 120 <= i <= 180:
        curve = -3.0
        height = math.cos(i * 0.08) * 1600
    elif 210 <= i <= 270:
        curve = 1.8
        height = math.sin(i * 0.15) * 800

    segments.append({
        "index": i,
        "p1": {"world": {"x": 0, "y": height, "z": i * SEGMENT_LENGTH}, "screen": {"x": 0, "y": 0, "w": 0}},
        "p2": {"world": {"x": 0, "y": (i + 1) * SEGMENT_LENGTH if i < 299 else (i + 1) * SEGMENT_LENGTH, "z": (i + 1) * SEGMENT_LENGTH}, "screen": {"x": 0, "y": 0, "w": 0}},
        "curve": curve,
        "color": "#161b22" if int(i / RUMBLE_LENGTH) % 2 == 0 else "#0d1117",
        "rumble": "#ff007f" if int(i / RUMBLE_LENGTH) % 2 == 0 else "#00f0ff"
    })

TRACK_LENGTH = len(segments) * SEGMENT_LENGTH

# --- Player State ---
player = {
    "x": 0.0,          # -1.0 (left side) to 1.0 (right side)
    "position": 0.0,   # Distance along track
    "speed": 0.0,      # Current speed
    "max_speed": 12000.0,
    "accel": 160.0,
    "braking": 350.0,
    "decel": 80.0,
    "off_road_decel": 300.0,
    "score": 0
}

keys = {"left": False, "right": False, "up": False, "down": False}

def on_keydown(e):
    k = e.key
    if k == "ArrowLeft" or k == "a" or k == "A": keys["left"] = True
    if k == "ArrowRight" or k == "d" or k == "D": keys["right"] = True
    if k == "ArrowUp" or k == "w" or k == "W": keys["up"] = True
    if k == "ArrowDown" or k == "s" or k == "S": keys["down"] = True

def on_keyup(e):
    k = e.key
    if k == "ArrowLeft" or k == "a" or k == "A": keys["left"] = False
    if k == "ArrowRight" or k == "d" or k == "D": keys["right"] = False
    if k == "ArrowUp" or k == "w" or k == "W": keys["up"] = False
    if k == "ArrowDown" or k == "s" or k == "S": keys["down"] = False

window.addEventListener("keydown", on_keydown)
window.addEventListener("keyup", on_keyup)

# --- Pseudo-3D Projection Helper ---
def project(p, camera_x, camera_y, camera_z, camera_depth):
    p["screen"]["x"] = 0
    p["screen"]["y"] = 0
    p["screen"]["w"] = 0

    wx = p["world"]["x"] - camera_x
    wy = p["world"]["y"] - camera_y
    wz = p["world"]["z"] - camera_z

    if wz > 0:
        scale = camera_depth / wz
        p["screen"]["x"] = math.round(HALF_W + (scale * wx * HALF_W))
        p["screen"]["y"] = math.round(HALF_H - (scale * wy * HALF_H))
        p["screen"]["w"] = math.round(scale * ROAD_WIDTH * HALF_W)

# Render Trapezoid Road Quad
def draw_poly(x1, y1, w1, x2, y2, w2, color):
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.moveTo(x1 - w1, y1)
    ctx.lineTo(x2 - w2, y2)
    ctx.lineTo(x2 + w2, y2)
    ctx.lineTo(x1 + w1, y1)
    ctx.closePath()
    ctx.fill()

state = {"frame": 0}

def frame(ts):
    state["frame"] = state["frame"] + 1
    
    # 1. Physics & Player Controls Update
    dt = 0.016
    
    # Steering
    if keys["left"]:
        player["x"] = player["x"] - 0.025 * (player["speed"] / player["max_speed"])
    if keys["right"]:
        player["x"] = player["x"] + 0.025 * (player["speed"] / player["max_speed"])

    # Accelerate / Brake / Decelerate
    if keys["up"]:
        player["speed"] = math.min(player["max_speed"], player["speed"] + player["accel"])
    elif keys["down"]:
        player["speed"] = math.max(0.0, player["speed"] - player["braking"])
    else:
        player["speed"] = math.max(0.0, player["speed"] - player["decel"])

    # Off-Road Penalty
    if (player["x"] < -1.0 or player["x"] > 1.0) and player["speed"] > 3000.0:
        player["speed"] = math.max(0.0, player["speed"] - player["off_road_decel"])

    # Advance distance
    player["position"] = (player["position"] + player["speed"] * dt) % TRACK_LENGTH
    player["score"] = player["score"] + int(player["speed"] * 0.001)

    # 2. Render Synthwave Skybox & Grid Ground
    ctx.fillStyle = "#0d0221"
    ctx.fillRect(0, 0, W, H)

    # Draw Neon Horizon Sun
    ctx.beginPath()
    ctx.arc(HALF_W, HALF_H - 20, 90, 0, math.pi * 2)
    ctx.fillStyle = "#ff007f"
    ctx.fill()

    # Horizon Line
    ctx.fillStyle = "#05010d"
    ctx.fillRect(0, HALF_H, W, HALF_H)

    # 3. Project and Render 3D Road
    start_pos = player["position"]
    start_index = int(start_pos / SEGMENT_LENGTH)
    cam_height = 1000.0
    cam_depth = 0.8
    
    dx = 0.0
    cam_x = player["x"] * ROAD_WIDTH
    
    # Draw segments back to front
    for n in range(80):
        idx = (start_index + n) % len(segments)
        segment = segments[idx]
        
        # Loop wrapping adjustment
        z_offset = TRACK_LENGTH if (start_index + n) >= len(segments) else 0.0
        
        dx = dx + segment["curve"]
        
        # Calculate camera relative coordinates
        p1_z = segment["p1"]["world"]["z"] + z_offset
        p2_z = segment["p2"]["world"]["z"] + z_offset
        
        project(segment["p1"], cam_x - dx, cam_height, start_pos, cam_depth)
        project(segment["p2"], cam_x - dx - segment["curve"], cam_height, start_pos, cam_depth)

        p1 = segment["p1"]["screen"]
        p2 = segment["p2"]["screen"]

        # Skip if behind camera or offscreen
        if p1["y"] <= p2["y"] or p2["y"] >= H or p1["y"] <= 0:
            continue

        # Draw Grass
        ctx.fillStyle = "#05010d" if int(idx / RUMBLE_LENGTH) % 2 == 0 else "#09021a"
        ctx.fillRect(0, p2["y"], W, p1["y"] - p2["y"])

        # Draw Rumble Strips
        draw_poly(p1["x"], p1["y"], p1["w"] * 1.15, p2["x"], p2["y"], p2["w"] * 1.15, segment["rumble"])

        # Draw Road Surface
        draw_poly(p1["x"], p1["y"], p1["w"], p2["x"], p2["y"], p2["w"], segment["color"])

        # Draw Center Line
        if int(idx / RUMBLE_LENGTH) % 2 == 0:
            draw_poly(p1["x"], p1["y"], p1["w"] * 0.04, p2["x"], p2["y"], p2["w"] * 0.04, "#ffe600")

    # 4. Render Player Car Sprite
    car_w, car_h = 80, 36
    car_x = HALF_W - car_w / 2
    car_y = H - 60

    # Draw Car Body (Synthwave Red/Cyan Sports Car)
    ctx.fillStyle = "#00f0ff"
    ctx.fillRect(car_x, car_y, car_w, car_h)
    ctx.fillStyle = "#ff0055"
    ctx.fillRect(car_x + 8, car_y + 6, car_w - 16, car_h - 14)
    # Taillights
    ctx.fillStyle = "#ff0000"
    ctx.fillRect(car_x + 6, car_y + car_h - 8, 18, 6)
    ctx.fillRect(car_x + car_w - 24, car_y + car_h - 8, 18, 6)

    # 5. Heads-Up Display (HUD)
    speed_mph = int((player["speed"] / player["max_speed"]) * 180)
    ctx.fillStyle = "#00f0ff"
    ctx.font = "bold 18px monospace"
    ctx.fillText(f"SPEED: {speed_mph} MPH", 25, 40)
    ctx.fillText(f"SCORE: {player['score']}", 25, 68)
    ctx.fillText("CONTROLS: ARROW KEYS or WASD", 25, 96)

    window.requestAnimationFrame(frame)

window.requestAnimationFrame(frame)
'''

# 1. Transpile Python Game Engine to JS
racer_js = transpile(RACER_PY, minify=True)

# 2. Build Standalone Interactive HTML Page
HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>3D Retro Synthwave Racer (Python Source)</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #05010d; font-family: monospace; color: #00f0ff; }}
  canvas {{ display: block; border-radius: 12px; box-shadow: 0 0 70px rgba(255,0,127,0.3); outline: none; }}
  .instructions {{ text-align: center; margin-top: 12px; font-size: 14px; color: #ff007f; }}
</style>
</head>
<body>
  <div>
    <canvas id="stage" width="800" height="500" tabindex="1"></canvas>
    <div class="instructions">Click game canvas & use <b>UP / DOWN / LEFT / RIGHT</b> to drive!</div>
  </div>
  <script>{racer_js}</script>
</body>
</html>
"""

out = Path(__file__).with_name("pyjs_racer.html")
out.write_text(HTML, encoding="utf-8")
print(f"Wrote {out} ({len(HTML)} bytes)")
