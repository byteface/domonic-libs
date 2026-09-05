from pathlib import Path
import myjs
from domonic_libs.pyjs import transpile

WEBGL_PY = r'''
import math
import random

W = 800
H = 500

stage = document.getElementById("stage")
gl = stage.getContext("webgl") or stage.getContext("experimental-webgl")

# --- GLSL Shaders ---
VS_SOURCE = """
attribute vec3 aPosition;
attribute vec3 aVelocity;

uniform mat4 uProjection;
uniform mat4 uModelView;
uniform vec2 uMouse;
uniform float uTime;

varying float vSpeed;

void main() {
    vec3 pos = aPosition;
    vec3 attractor = vec3(uMouse.x * 4.0, uMouse.y * 2.5, 0.0);
    vec3 delta = attractor - pos;
    float dist = length(delta);
    
    if (dist > 0.1) {
        pos += normalize(delta) * (1.5 / (dist * dist + 0.5)) * sin(uTime * 2.0);
    }

    vSpeed = length(aVelocity) + (2.0 / (dist + 0.2));

    vec4 mvPosition = uModelView * vec4(pos, 1.0);
    gl_Position = uProjection * mvPosition;
    gl_PointSize = max(1.5, (12.0 / -mvPosition.z));
}
"""

FS_SOURCE = """
precision mediump float;
varying float vSpeed;

void main() {
    float dist = length(gl_PointCoord - vec2(0.5));
    if (dist > 0.5) discard;
    
    float alpha = (1.0 - dist * 2.0);
    
    // Dynamic velocity hue shift (Cyan -> Magenta -> Gold)
    vec3 color = mix(vec3(0.0, 0.9, 1.0), vec3(1.0, 0.0, 0.5), min(1.0, vSpeed * 0.3));
    color = mix(color, vec3(1.0, 0.8, 0.2), min(1.0, vSpeed * 0.1));

    gl_FragColor = vec4(color, alpha * 0.85);
}
"""

def create_shader(gl_ctx, type_val, source):
    shader = gl_ctx.createShader(type_val)
    gl_ctx.shaderSource(shader, source)
    gl_ctx.compileShader(shader)
    if not gl_ctx.getShaderParameter(shader, gl_ctx.COMPILE_STATUS):
        print(gl_ctx.getShaderInfoLog(shader))
    return shader

vert_shader = create_shader(gl, gl.VERTEX_SHADER, VS_SOURCE)
frag_shader = create_shader(gl, gl.FRAGMENT_SHADER, FS_SOURCE)

program = gl.createProgram()
gl.attachShader(program, vert_shader)
gl.attachShader(program, frag_shader)
gl.linkProgram(program)

if gl.getProgramParameter(program, gl.LINK_STATUS):
    gl.useProgram(program)

PARTICLE_COUNT = 5000
positions = []
velocities = []

for _ in range(PARTICLE_COUNT):
    rad = random.uniform(0.5, 3.8)
    theta = random.uniform(0, math.pi * 2)
    phi = random.uniform(-0.5, 0.5)

    positions.append(math.cos(theta) * rad)
    positions.append(math.sin(theta) * rad)
    positions.append(phi)

    velocities.append(-math.sin(theta) * 0.8)
    velocities.append(math.cos(theta) * 0.8)
    velocities.append(random.uniform(-0.1, 0.1))

pos_buffer = gl.createBuffer()
gl.bindBuffer(gl.ARRAY_BUFFER, pos_buffer)
gl.bufferData(gl.ARRAY_BUFFER, Float32Array.new(positions), gl.DYNAMIC_DRAW)

aPosition = gl.getAttribLocation(program, "aPosition")
if aPosition >= 0:
    gl.enableVertexAttribArray(aPosition)
    gl.vertexAttribPointer(aPosition, 3, gl.FLOAT, False, 0, 0)

vel_buffer = gl.createBuffer()
gl.bindBuffer(gl.ARRAY_BUFFER, vel_buffer)
gl.bufferData(gl.ARRAY_BUFFER, Float32Array.new(velocities), gl.STATIC_DRAW)

aVelocity = gl.getAttribLocation(program, "aVelocity")
if aVelocity >= 0:
    gl.enableVertexAttribArray(aVelocity)
    gl.vertexAttribPointer(aVelocity, 3, gl.FLOAT, False, 0, 0)

uProjection = gl.getUniformLocation(program, "uProjection")
uModelView = gl.getUniformLocation(program, "uModelView")
uMouse = gl.getUniformLocation(program, "uMouse")
uTime = gl.getUniformLocation(program, "uTime")

mouse = {"x": 0.0, "y": 0.0}

state = {"frame": 0}

def get_perspective_matrix(fovy, aspect, near, far):
    f = 1.0 / math.tan(fovy / 2.0)
    nf = 1.0 / (near - far)
    return [
        f / aspect, 0.0, 0.0, 0.0,
        0.0, f, 0.0, 0.0,
        0.0, 0.0, (far + near) * nf, -1.0,
        0.0, 0.0, (2.0 * far * near) * nf, 0.0
    ]

proj_matrix = get_perspective_matrix(math.pi / 4.0, W / H, 0.1, 100.0)
if uProjection:
    gl.uniformMatrix4fv(uProjection, False, Float32Array.new(proj_matrix))

gl.enable(gl.BLEND)
gl.blendFunc(gl.SRC_ALPHA, gl.ONE)

def frame(ts):
    state["frame"] = state["frame"] + 1
    t = state["frame"] * 0.015

    m_x, m_y = mouse["x"] * 4.0, mouse["y"] * 2.5
    
    for i in range(PARTICLE_COUNT):
        idx = i * 3
        px, py, pz = positions[idx], positions[idx + 1], positions[idx + 2]
        vx, vy, vz = velocities[idx], velocities[idx + 1], velocities[idx + 2]

        dx = m_x - px
        dy = m_y - py
        dist_sq = dx * dx + dy * dy + 0.1
        force = 0.005 / dist_sq

        vx = vx + dx * force
        vy = vy + dy * force

        positions[idx] = px + vx * 0.016
        positions[idx + 1] = py + vy * 0.016
        positions[idx + 2] = pz + vz * 0.016

        velocities[idx] = vx * 0.99
        velocities[idx + 1] = vy * 0.99
        velocities[idx + 2] = vz * 0.99

    gl.bindBuffer(gl.ARRAY_BUFFER, pos_buffer)
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, Float32Array.new(positions))

    cos_t, sin_t = math.cos(t * 0.3), math.sin(t * 0.3)
    mv_matrix = [
        cos_t, 0.0, sin_t, 0.0,
        0.0, 1.0, 0.0, 0.0,
        -sin_t, 0.0, cos_t, 0.0,
        0.0, 0.0, -6.5, 1.0
    ]
    
    if uModelView: gl.uniformMatrix4fv(uModelView, False, Float32Array.new(mv_matrix))
    if uMouse: gl.uniform2f(uMouse, mouse["x"], mouse["y"])
    if uTime: gl.uniform1f(uTime, t)

    gl.viewport(0, 0, W, H)
    gl.clearColor(0.02, 0.03, 0.06, 1.0)
    
    # Explicit integer argument passed to fix clear call
    gl.clear(16384)  # 16384 == gl.COLOR_BUFFER_BIT

    gl.drawArrays(gl.POINTS, 0, PARTICLE_COUNT)
    window.requestAnimationFrame(frame)

window.requestAnimationFrame(frame)
'''

webgl_js = transpile(WEBGL_PY, minify=True)

HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Fixed WebGL Engine</title>
<style>
  body {{ margin: 0; background: #03050a; display: grid; place-items: center; min-height: 100vh; }}
  canvas {{ display: block; border-radius: 12px; }}
</style>
</head>
<body>
  <canvas id="stage" width="800" height="500"></canvas>
  <script>{webgl_js}</script>
</body>
</html>
"""

out = Path(__file__).with_name("pyjs_webgl.html")
out.write_text(HTML, encoding="utf-8")
print(f"Wrote {out}")

# TODO - moderngl