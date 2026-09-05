from collections import Counter
from pathlib import Path

import myjs
from domonic_libs.pyjs import transpile

# ---------------------------------------------------------------------------
# Self-Driving Neural Car with Steering Physics -- Written in Pure Python
# ---------------------------------------------------------------------------
AI_CAR_PY = r'''
import math
import random

W = 800
H = 500
stage = document.getElementById("stage")
ctx = stage.getContext("2d")

track_center = {"x": W / 2, "y": H / 2, "rx": 300, "ry": 180}

class NeuralNetwork:
    def __init__(self, weights=None):
        if weights:
            self.w_hidden = weights["hidden"]
            self.w_output = weights["output"]
        else:
            # Random initial weights
            self.w_hidden = []
            for i in range(5):
                row = []
                for j in range(4):
                    row.append(random.uniform(-1.0, 1.0))
                self.w_hidden.append(row)

            self.w_output = []
            for j in range(4):
                row = []
                for k in range(2):
                    row.append(random.uniform(-1.0, 1.0))
                self.w_output.append(row)

    def feed_forward(self, inputs):
        hidden = [0.0, 0.0, 0.0, 0.0]
        for j in range(4):
            sum_val = 0.0
            for i in range(5):
                sum_val = sum_val + inputs[i] * self.w_hidden[i][j]
            hidden[j] = math.tanh(sum_val)

        outputs = [0.0, 0.0]
        for k in range(2):
            sum_val = 0.0
            for j in range(4):
                sum_val = sum_val + hidden[j] * self.w_output[j][k]
            outputs[k] = math.tanh(sum_val)
            
        return outputs

class Car:
    def __init__(self, brain=None):
        self.x = W / 2
        self.y = H / 2 - 180
        self.angle = 0.0
        self.speed = 3.0
        self.alive = True
        self.fitness = 0.0
        self.sensors = [1.0, 1.0, 1.0, 1.0, 1.0]
        self.brain = brain if brain else NeuralNetwork()

    def update_sensors(self):
        angles = [-1.05, -0.52, 0.0, 0.52, 1.05]
        for idx in range(5):
            ray_angle = self.angle + angles[idx]
            dist = 1.0
            for step in range(1, 16):
                rx = self.x + math.cos(ray_angle) * (step * 8)
                ry = self.y + math.sin(ray_angle) * (step * 8)
                
                dx = (rx - track_center["x"]) / track_center["rx"]
                dy = (ry - track_center["y"]) / track_center["ry"]
                ellipse_dist = math.sqrt(dx * dx + dy * dy)
                
                # Check track collision
                if ellipse_dist < 0.65 or ellipse_dist > 1.15:
                    dist = (step * 8) / 120.0
                    break
            self.sensors[idx] = dist

    def step(self):
        if not self.alive:
            return

        self.update_sensors()
        
        # Check crash condition
        if self.sensors[2] < 0.15 or self.sensors[0] < 0.1 or self.sensors[4] < 0.1:
            self.alive = False
            return

        outputs = self.brain.feed_forward(self.sensors)
        
        # Stronger steering response
        steer = outputs[0] * 0.12
        accel = outputs[1] * 0.1
        
        self.angle = self.angle + steer
        self.speed = math.max(1.5, math.min(4.5, self.speed + accel))
        
        self.x = self.x + math.cos(self.angle) * self.speed
        self.y = self.y + math.sin(self.angle) * self.speed
        self.fitness = self.fitness + self.speed

# Population setup
POP_SIZE = 15
population = []
for _ in range(POP_SIZE):
    population.append(Car())

generation = 1

def frame(ts):
    alive_count = 0
    for car in population:
        if car.alive:
            car.step()
            alive_count = alive_count + 1

    # Clear Background
    ctx.fillStyle = "#0d1117"
    ctx.fillRect(0, 0, W, H)

    # Draw Racetrack
    ctx.beginPath()
    ctx.ellipse(track_center["x"], track_center["y"], track_center["rx"], track_center["ry"], 0, 0, math.pi * 2)
    ctx.strokeStyle = "#30363d"
    ctx.lineWidth = 90
    ctx.stroke()

    # Draw Cars & Sensors
    for car in population:
        if not car.alive:
            continue
            
        # Draw Sensors for active cars
        angles = [-1.05, -0.52, 0.0, 0.52, 1.05]
        for i in range(5):
            s_dist = car.sensors[i] * 120.0
            r_angle = car.angle + angles[i]
            ctx.beginPath()
            ctx.moveTo(car.x, car.y)
            ctx.lineTo(car.x + math.cos(r_angle) * s_dist, car.y + math.sin(r_angle) * s_dist)
            ctx.strokeStyle = f"hsla({int(car.sensors[i] * 120)}, 100%, 50%, 0.4)"
            ctx.lineWidth = 1
            ctx.stroke()

        # Draw Car Body
        ctx.save()
        ctx.translate(car.x, car.y)
        ctx.rotate(car.angle)
        ctx.fillStyle = "#58a6ff"
        ctx.fillRect(-10, -5, 20, 10)
        ctx.restore()

    # HUD
    ctx.fillStyle = "#f0f6fc"
    ctx.font = "14px monospace"
    ctx.fillText(f"Gen: {generation} | Alive: {alive_count}/{POP_SIZE}", 20, 30)

    window.requestAnimationFrame(frame)

window.requestAnimationFrame(frame)
'''

# 1. Transpile Python logic to JavaScript
ai_car_js = transpile(AI_CAR_PY, minify=True)

# 2. Build HTML Page
HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AI Neural Car Population (Python Source)</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #010409; font-family: monospace; color: #58a6ff; }}
  canvas {{ display: block; border-radius: 12px; box-shadow: 0 0 60px rgba(88,166,255,0.15); }}
</style>
</head>
<body>
  <div>
    <canvas id="stage" width="800" height="500"></canvas>
  </div>
  <script>{ai_car_js}</script>
</body>
</html>
"""

out = Path(__file__).with_name("pyjs_ai_car.html")
out.write_text(HTML, encoding="utf-8")
print(f"Wrote {out} ({len(HTML)} bytes)")
