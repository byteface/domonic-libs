from collections import Counter
from pathlib import Path

import myjs
from domonic_libs.pyjs import transpile

# ---------------------------------------------------------------------------
# Generative Audio Synth & Visualizer -- Written in Pure Python
# ---------------------------------------------------------------------------
SYNTH_PY = r'''
import math
import random

W = 800
H = 400
stage = document.getElementById("stage")
ctx = stage.getContext("2d")

# Web Audio API Nodes created directly from Python syntax
AudioContext = window.AudioContext or window.webkitAudioContext
audio_ctx = AudioContext()

# Pentatonic scale frequencies for musical randomness
SCALE = [130.81, 146.83, 164.81, 196.00, 220.00, 261.63, 293.66, 329.63, 392.00]

state = {
    "frame": 0,
    "nodes": [],
    "history": []
}

def play_tone(freq, type_name, duration):
    # Create Web Audio Nodes
    osc = audio_ctx.createOscillator()
    gain = audio_ctx.createGain()

    osc.type = type_name
    osc.frequency.value = freq

    # Envelope: Fade out gain over duration
    now = audio_ctx.currentTime
    gain.gain.setValueAtTime(0.3, now)
    gain.gain.exponentialRampToValueAtTime(0.001, now + duration)

    osc.connect(gain)
    gain.connect(audio_ctx.destination)

    osc.start(now)
    osc.stop(now + duration)

    # Store active voice metadata for the visualizer
    state["nodes"].append({
        "freq": freq,
        "x": (freq / 500.0) * W,
        "y": H / 2,
        "radius": 10,
        "max_radius": 120,
        "hue": int((freq * 1.7) % 360)
    })

def frame(ts):
    state["frame"] = state["frame"] + 1
    f = state["frame"]

    # Generative music trigger: trigger tones on rhythmic intervals
    if f % 12 == 1:
        note_idx = random.randint(0, len(SCALE) - 1)
        freq = SCALE[note_idx]
        wave_types = ["sine", "triangle", "square"]
        wave = wave_types[random.randint(0, len(wave_types) - 1)]
        play_tone(freq, wave, 0.8)

    # Render Visualizer Canvas
    ctx.fillStyle = "rgba(5, 7, 15, 0.2)"  # Trail effect
    ctx.fillRect(0, 0, W, H)

    # Draw Audio Pulses
    active_nodes = []
    for node in state["nodes"]:
        node["radius"] = node["radius"] + 3.5
        alpha = 1.0 - (node["radius"] / node["max_radius"])

        if alpha > 0:
            ctx.beginPath()
            ctx.arc(node["x"], node["y"], node["radius"], 0, math.pi * 2)
            ctx.strokeStyle = f"hsla({node['hue']}, 90%, 60%, {alpha})"
            ctx.lineWidth = 3
            ctx.stroke()
            active_nodes.append(node)

    state["nodes"] = active_nodes

    # Draw Audio Waveform Bar across bottom
    ctx.fillStyle = "#89b4fa"
    for i in range(0, W, 16):
        bar_h = math.sin((f * 0.1) + (i * 0.05)) * 25 + 30
        ctx.fillRect(i, H - bar_h, 12, bar_h)

    window.requestAnimationFrame(frame)

# Start interactive user gesture unlock
def start_synth(e):
    if audio_ctx.state == "suspended":
        audio_ctx.resume()
    window.requestAnimationFrame(frame)

window.addEventListener("click", start_synth)
window.requestAnimationFrame(frame)
'''

# 1. Transpile Python logic to JavaScript
synth_js = transpile(SYNTH_PY, minify=True)

# 2. Build HTML page
HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Web Audio Synth + Visualizer (Python Source)</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #05070f; font-family: sans-serif; color: #a6adc8; }}
  canvas {{ display: block; border-radius: 12px; box-shadow: 0 0 50px rgba(137,180,250,0.2); cursor: pointer; }}
  p {{ text-align: center; margin-top: 1rem; }}
</style>
</head>
<body>
  <div>
    <canvas id="stage" width="800" height="400"></canvas>
    <p>Click anywhere to unlock audio output</p>
  </div>
  <script>{synth_js}</script>
</body>
</html>
"""

out = Path(__file__).with_name("pyjs_synth.html")
out.write_text(HTML, encoding="utf-8")
print(f"Wrote {out} ({len(HTML)} bytes)")
