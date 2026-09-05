// A real native window (raylib, via ffi) -- a button wired to a JS onclick.
//   myjs examples/myjs/raylib.js   (brew install raylib)
//   click the button; it auto-closes after ~6s so this runs unattended too

// raylib passes colors/rects as C structs by value -- ctypes handles that
// side; the actual frame loop, hit-testing, and JS event wiring below is
// plain JS calling straight through to it.
const rl = py.exec(`
import ctypes, ctypes.util

class _Color(ctypes.Structure):
    _fields_ = [("r", ctypes.c_ubyte), ("g", ctypes.c_ubyte), ("b", ctypes.c_ubyte), ("a", ctypes.c_ubyte)]

_lib = ctypes.CDLL(ctypes.util.find_library("raylib"))
_lib.InitWindow.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p]
_lib.WindowShouldClose.restype = ctypes.c_bool
_lib.DrawRectangle.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, _Color]
_lib.DrawText.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, _Color]
_lib.ClearBackground.argtypes = [_Color]
_lib.GetMouseX.restype = ctypes.c_int
_lib.GetMouseY.restype = ctypes.c_int
_lib.IsMouseButtonPressed.restype = ctypes.c_bool

def init_window(w, h, title): _lib.InitWindow(w, h, title.encode())
def should_close(): return bool(_lib.WindowShouldClose())
def begin(): _lib.BeginDrawing()
def end(): _lib.EndDrawing()
def set_fps(n): _lib.SetTargetFPS(n)
def clear(r, g, b): _lib.ClearBackground(_Color(r, g, b, 255))
def rect(x, y, w, h, r, g, b): _lib.DrawRectangle(x, y, w, h, _Color(r, g, b, 255))
def text(s, x, y, size, r, g, b): _lib.DrawText(s.encode(), x, y, size, _Color(r, g, b, 255))
def mouse_x(): return _lib.GetMouseX()
def mouse_y(): return _lib.GetMouseY()
def mouse_clicked(): return bool(_lib.IsMouseButtonPressed(0))
def close(): _lib.CloseWindow()
`);

// --- a tiny scene, described the DOM way: a plain object with an onclick --
const button = { x: 150, y: 120, w: 100, h: 40, label: "Click me", clicks: 0 };
button.onclick = () => {
  button.clicks++;
  button.label = `Clicked ${button.clicks}!`;
};

function hitTest(mx, my, b) {
  return mx >= b.x && mx <= b.x + b.w && my >= b.y && my <= b.y + b.h;
}

rl.init_window(400, 300, "myjs + raylib");
rl.set_fps(60);

let frame = 0;
while (!rl.should_close() && frame < 360) {   // ~6s at 60fps -- runs unattended too
  frame++;

  if (rl.mouse_clicked() && hitTest(rl.mouse_x(), rl.mouse_y(), button)) {
    button.onclick();   // a real native click firing a real JS handler
  }

  rl.begin();
  rl.clear(30, 30, 46);
  rl.text("Hello from JavaScript, drawn by a native C library", 20, 20, 16, 220, 220, 220);
  rl.rect(button.x, button.y, button.w, button.h, 68, 120, 210);
  rl.text(button.label, button.x + 10, button.y + 12, 16, 255, 255, 255);
  rl.text(`frame ${frame}`, 20, 260, 14, 120, 120, 130);
  rl.end();
}

rl.close();
console.log(`Window closed after ${frame} frames. Button was clicked ${button.clicks} time(s).`);
