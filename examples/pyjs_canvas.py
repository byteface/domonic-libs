"""A canvas animation written in Python -> one self-contained HTML file.

    python examples/pyjs_canvas.py

The animation below is real Python: a ``Spark`` particle class with a little
physics, and a per-pixel plasma field written straight into the canvas pixel
buffer -- the kind of loop you'd normally hand to numpy. `domonic_libs.pyjs`
transpiles the module to JavaScript (``import math`` / ``import random`` map
onto ``Math`` and a ``__py`` shim), this script inlines it into a single
``.html`` file, and then -- to prove the browser APIs really get called -- it
loads the page with `myjs.Page`, advances a few animation frames headlessly,
and reads back the canvas' recorded draw calls.

Open ``pyjs_canvas.html`` in a browser afterwards; it's the same code, running
continuously.
"""

from collections import Counter
from pathlib import Path

import myjs
from domonic_libs.pyjs import transpile

# ---------------------------------------------------------------------------
# the animation -- plain Python. `document` / `window` / the 2D context and
# `requestAnimationFrame` are the browser's; `math` / `random` are Python's.
# ---------------------------------------------------------------------------
ANIM_PY = r'''
import math
import random

W = 720
H = 405

stage = document.getElementById("stage")
ctx = stage.getContext("2d")

# a small offscreen canvas the plasma is painted into, then scaled up
off = document.createElement("canvas")
off.width = 96
off.height = 54
octx = off.getContext("2d")

S = {"frame": 0, "sparks": []}


class Spark:
    def __init__(self, x, y):
        angle = random.random() * math.pi * 2
        speed = random.uniform(1.5, 6.0)
        self.x = x
        self.y = y
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = 1.0
        self.hue = random.randint(0, 359)

    def alive(self):
        return self.life > 0.02

    def step(self):
        self.vy = self.vy + 0.12          # gravity
        self.vx = self.vx * 0.99          # drag
        self.x = self.x + self.vx
        self.y = self.y + self.vy
        self.life = self.life - 0.011
        if self.y > H - 3:                # floor bounce
            self.y = H - 3
            self.vy = -self.vy * 0.55
        if self.x < 0 or self.x > W:      # wall bounce
            self.vx = -self.vx * 0.7

    def draw(self):
        radius = 1.5 + self.life * 4
        ctx.globalAlpha = self.life
        ctx.fillStyle = f"hsl({self.hue}, 95%, {int(45 + self.life * 30)}%)"
        ctx.beginPath()
        ctx.arc(self.x, self.y, radius, 0, math.pi * 2)
        ctx.fill()


def plasma(t):
    # per-pixel bitmap work: three sine fields summed into the RGBA buffer,
    # written one byte at a time, then blitted and scaled to fill the stage.
    img = octx.createImageData(off.width, off.height)
    data = img.data
    i = 0
    for py in range(off.height):
        for px in range(off.width):
            v = (math.sin(px * 0.11 + t)
                 + math.sin(py * 0.13 - t * 0.7)
                 + math.sin((px + py) * 0.08 + t * 1.3))
            c = (v + 3) / 6                       # -> 0..1
            data[i] = int(18 + c * 55)
            data[i + 1] = int(8 + c * 38)
            data[i + 2] = int(55 + c * 165)
            data[i + 3] = 255
            i = i + 4
    octx.putImageData(img, 0, 0)
    ctx.drawImage(off, 0, 0, W, H)


def burst(x, y, n):
    for _ in range(n):
        S["sparks"].append(Spark(x, y))


def frame(ts):
    S["frame"] = S["frame"] + 1
    f = S["frame"]

    ctx.globalAlpha = 1
    plasma(f * 0.04)

    if f % 20 == 1:
        burst(random.randint(120, W - 120), random.randint(70, 230), 44)

    keep = []
    for p in S["sparks"]:
        p.step()
        if p.alive():
            p.draw()
            keep.append(p)
    S["sparks"] = keep

    ctx.globalAlpha = 1
    document.getElementById("hud").textContent = (
        f"frame {f}  ·  {len(S['sparks'])} sparks alive")
    window.requestAnimationFrame(frame)


burst(W / 2, H / 2, 90)
window.requestAnimationFrame(frame)
'''

ANIM_JS = transpile(ANIM_PY, minify=True)

HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>sparks + plasma (written in Python)</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #05060a; color: #cdd6f4;
         font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }}
  figure {{ margin: 0; }}
  canvas {{ display: block; border-radius: 10px; box-shadow: 0 20px 60px rgba(0,0,0,.6);
            max-width: 92vw; height: auto; }}
  figcaption {{ margin-top: .9rem; display: flex; justify-content: space-between;
               color: #6c7086; }}
  #hud {{ color: #a6adc8; }}
</style>
</head>
<body>
  <figure>
    <canvas id="stage" width="720" height="405"></canvas>
    <figcaption>
      <span>particle physics + per-pixel plasma &mdash; logic transpiled from Python</span>
      <span id="hud">starting&hellip;</span>
    </figcaption>
  </figure>
  <script>{ANIM_JS}</script>
</body>
</html>
"""

out = Path(__file__).with_name("pyjs_canvas.html")
out.write_text(HTML, encoding="utf-8")
print(f"wrote {out}  ({len(HTML)} bytes, {len(ANIM_JS)} of it transpiled JS)")
print("open it in a browser for the live animation, or watch it run headless below:\n")

# ---------------------------------------------------------------------------
# drive the page headlessly -- proof the canvas API actually gets called
# ---------------------------------------------------------------------------
page = myjs.Page.load(str(out))
assert not page.errors, page.errors

ctx = page.query("#stage").getContext("2d")   # domonic's recording 2D context


def snap(label):
    kinds = Counter(c["name"] for c in ctx.commands)
    tally = "  ".join(f"{k}×{n}" for k, n in sorted(kinds.items()))
    print(f"  {label:<16} {page.text('#hud'):<26} {tally}")
    ctx.commands.clear()


snap("loaded")
page.frames(1)
snap("frame 1")
page.frames(19)
snap("frames 2-20")
page.frames(20)
snap("frames 21-40")

# the plasma path: one createImageData + putImageData + drawImage per frame,
# each preceded by a full width*height byte-loop in the Python source
octx = page.eval("off.getContext('2d')")
w, h = page.eval("off.width"), page.eval("off.height")
puts = sum(c["name"] == "putImageData" for c in octx.commands)
print(f"\n  plasma: {puts} ImageData frames blitted, "
      f"{w * h} px ({w * h * 4} byte-writes) per frame from the Python loop")
