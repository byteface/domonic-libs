// A real website's real physics, fetched live, run completely unmodified.
//   myjs examples/myjs/atoms.js   (needs raylib: brew install raylib)
//
// byteface.github.io's actual "Atom Simulation" -- the real Particle class,
// real repulsion/attraction forces -- rendered with raylib circles instead
// of its <canvas> (domonic's canvas 2D methods exist but don't rasterize
// yet, so this swaps only the drawing step, not the physics). Auto-closes
// after ~6s so this runs unattended too.

const SRC_URL = "https://byteface.github.io/static/js/pages/2d.min.js";

console.log(`Fetching real physics from ${SRC_URL} ...`);
const src = fetchSync(SRC_URL).text();
eval(src);   // defines the real, live Class + Particle -- nothing rewritten
console.log(`Loaded. typeof Particle = ${typeof Particle} (the actual class from the site).`);

const W = 500, H = 500;
const N = 40;
const atoms = [];

for (let i = 0; i < N; i++) {
  const p = new Particle();
  p.setBounds({ xMin: 0, yMin: 0, xMax: W, yMax: H });
  p.x = Math.random() * W;
  p.y = Math.random() * H;
  p.damp = 0.9;
  p.maxSpeed = 6;
  atoms.push(p);
}
// the same "tell every atom about every other atom" step the real page does
for (const a of atoms) {
  for (const b of atoms) {
    if (a !== b) {
      a.addRepelParticle(b, 400, 40);
      a.addGravParticle(b, 300);
    }
  }
}
console.log(`${N} real Particle instances, real mutual repel/attract forces wired up.`);

const rl = py.exec(`
import ctypes, ctypes.util
class _Color(ctypes.Structure):
    _fields_ = [("r", ctypes.c_ubyte), ("g", ctypes.c_ubyte), ("b", ctypes.c_ubyte), ("a", ctypes.c_ubyte)]
_lib = ctypes.CDLL(ctypes.util.find_library("raylib"))
_lib.InitWindow.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p]
_lib.WindowShouldClose.restype = ctypes.c_bool
_lib.DrawCircle.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_float, _Color]
_lib.ClearBackground.argtypes = [_Color]

def init_window(title, w, h): _lib.InitWindow(w, h, title.encode())
def should_close(): return bool(_lib.WindowShouldClose())
def set_fps(n): _lib.SetTargetFPS(n)
def begin(): _lib.BeginDrawing()
def end(): _lib.EndDrawing()
def clear(r, g, b): _lib.ClearBackground(_Color(r, g, b, 255))
def circle(x, y, radius, r, g, b, a): _lib.DrawCircle(int(x), int(y), radius, _Color(r, g, b, a))
def close(): _lib.CloseWindow()
`);

rl.init_window("myjs: your real Atom Simulation physics, native window", W, H);
rl.set_fps(60);

let frame = 0;
while (!rl.should_close() && frame < 360) {   // ~6s at 60fps -- runs unattended too
  frame++;
  for (const p of atoms) p.update();          // the real, unmodified physics

  rl.begin();
  rl.clear(10, 12, 20);
  for (const p of atoms) rl.circle(p.x, p.y, 6, 70, 160, 255, 220);
  rl.end();
}

rl.close();
console.log(`Closed after ${frame} frames -- ${N} real atoms, real physics, real window.`);
