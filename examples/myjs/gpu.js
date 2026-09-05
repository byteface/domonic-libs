// Zero-copy GPU texture updates straight from live Python compute.
//   myjs examples/myjs/gpu.js   (needs raylib + numpy: brew install raylib, pip install numpy)
//
// A numpy array's raw memory address, handed through ffi, IS the texture
// data -- JS never copies a single pixel, it only ever passes the pointer
// along. Auto-closes after ~4s so this runs unattended too.

const rl = py.exec(`
import ctypes, ctypes.util
import numpy as np

class _Color(ctypes.Structure):
    _fields_ = [("r", ctypes.c_ubyte), ("g", ctypes.c_ubyte), ("b", ctypes.c_ubyte), ("a", ctypes.c_ubyte)]

class _Image(ctypes.Structure):
    _fields_ = [("data", ctypes.c_void_p), ("width", ctypes.c_int), ("height", ctypes.c_int),
                ("mipmaps", ctypes.c_int), ("format", ctypes.c_int)]

class _Texture2D(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint), ("width", ctypes.c_int), ("height", ctypes.c_int),
                ("mipmaps", ctypes.c_int), ("format", ctypes.c_int)]

_PIXELFORMAT_R8G8B8A8 = 7
_lib = ctypes.CDLL(ctypes.util.find_library("raylib"))
_lib.InitWindow.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p]
_lib.WindowShouldClose.restype = ctypes.c_bool
_lib.LoadTextureFromImage.argtypes = [_Image]
_lib.LoadTextureFromImage.restype = _Texture2D
_lib.UpdateTexture.argtypes = [_Texture2D, ctypes.c_void_p]
_lib.DrawTexture.argtypes = [_Texture2D, ctypes.c_int, ctypes.c_int, _Color]
_lib.ClearBackground.argtypes = [_Color]

_buf = None
_tex = None

def init_window(title, w, h): _lib.InitWindow(w, h, title.encode())
def should_close(): return bool(_lib.WindowShouldClose())
def set_fps(n): _lib.SetTargetFPS(n)
def begin(): _lib.BeginDrawing()
def end(): _lib.EndDrawing()
def clear(r, g, b): _lib.ClearBackground(_Color(r, g, b, 255))
def draw_texture(x, y): _lib.DrawTexture(_tex, x, y, _Color(255, 255, 255, 255))
def close(): _lib.CloseWindow()

def make_texture(w, h):
    # this buffer's own memory becomes the texture's memory -- no copy, ever
    global _buf, _tex
    _buf = np.zeros((h, w, 4), dtype=np.uint8)
    _buf[:, :, 3] = 255
    image = _Image(ctypes.c_void_p(_buf.ctypes.data), w, h, 1, _PIXELFORMAT_R8G8B8A8)
    _tex = _lib.LoadTextureFromImage(image)
    return _tex.id

def render_frame(t):
    # a real, changing Python computation -- mutates the SAME buffer in place
    w, h = _buf.shape[1], _buf.shape[0]
    _buf[:, :, 0] = (np.arange(w) + t * 3) % 256
    _buf[:, :, 1] = (np.arange(h)[:, None] + t * 2) % 256
    _buf[:, :, 2] = np.random.randint(0, 255, (h, w), dtype=np.uint8)
    _lib.UpdateTexture(_tex, ctypes.c_void_p(_buf.ctypes.data))   # zero-copy re-upload
`);

const W = 320, H = 240;
rl.init_window("myjs + GPU: zero-copy numpy texture", 640, 480);
rl.set_fps(30);

const texId = rl.make_texture(W, H);
console.log(`Texture id=${texId}, ${W}x${H} -- backed directly by a live numpy array's own memory.`);

let frame = 0;
while (!rl.should_close() && frame < 120) {   // ~4s at 30fps -- runs unattended too
  frame++;
  rl.render_frame(frame);   // Python mutates the buffer; JS never touches the pixels
  rl.begin();
  rl.clear(15, 15, 25);
  rl.draw_texture(160, 120);
  rl.end();
}

rl.close();
console.log(`Closed after ${frame} frames -- every one uploaded straight from Python's own memory, zero copies.`);
