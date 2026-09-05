// Turn a DOM into a real image file -- rasterize it, pack real BMP bytes.
//   myjs examples/myjs/snapshot.js
//
// Not a browser's rendering pipeline -- there's no CSS box model here -- but
// it's a genuine DOM -> real, valid image file path: a <canvas> element with
// <rect> children (attributes only), walked and painted into a pixel grid,
// packed into a real .bmp with `struct` and a `Uint8Array` -- no Python glue.

const W = 120, H = 80;

const canvas = document.createElement("canvas");
canvas.setAttribute("width", W);
canvas.setAttribute("height", H);

function rect(x, y, w, h, color) {
  const el = document.createElement("rect");
  el.setAttribute("x", x);
  el.setAttribute("y", y);
  el.setAttribute("width", w);
  el.setAttribute("height", h);
  el.setAttribute("fill", color);
  canvas.appendChild(el);
  return el;
}

// a little sunset, entirely described as DOM elements + attributes
rect(0, 0, W, H, "#1e2a3a");        // sky
rect(0, 45, W, H - 45, "#274b6d");  // sea
rect(50, 18, 22, 22, "#f4b942");    // sun
rect(0, H - 12, W, 12, "#0d1622");  // shore

console.log(`Scene   : ${canvas.children.length} DOM elements, described with document.createElement + setAttribute.`);

// --- rasterize: walk the DOM, paint each <rect> into a pixel grid ----------
function hexToRgb(hex) {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

const pixels = Array.from({ length: H }, () => Array.from({ length: W }, () => [0, 0, 0]));

for (const el of canvas.children) {
  const x = Number(el.getAttribute("x")), y = Number(el.getAttribute("y"));
  const w = Number(el.getAttribute("width")), h = Number(el.getAttribute("height"));
  const [r, g, b] = hexToRgb(el.getAttribute("fill"));
  for (let yy = Math.max(0, y); yy < Math.min(H, y + h); yy++) {
    for (let xx = Math.max(0, x); xx < Math.min(W, x + w); xx++) {
      pixels[yy][xx] = [r, g, b];
    }
  }
}

console.log(`Raster  : ${W}x${H} pixel grid, painted in plain JS (no canvas library).`);

// --- pack real BMP bytes: `struct` for the numeric header fields, plain
// byte math for everything else -- rows are bottom-up, BGR, 4-byte padded
const rowSize = Math.ceil((W * 3) / 4) * 4;
const imageSize = rowSize * H;
const pixelOffset = 14 + 40;
const fileSize = pixelOffset + imageSize;

const fileHeader = struct.pack("<IHHI", fileSize, 0, 0, pixelOffset);         // after the "BM" signature
const dibHeader = struct.pack("<IiiHHIIiiII", 40, W, H, 1, 24, 0, imageSize, 2835, 2835, 0, 0);

const buf = new Uint8Array(fileSize);   // zero-filled -- row padding is free
let o = 0;
buf[o++] = "B".charCodeAt(0);
buf[o++] = "M".charCodeAt(0);
for (let i = 0; i < fileHeader.length; i++) buf[o++] = fileHeader[i];
for (let i = 0; i < dibHeader.length; i++) buf[o++] = dibHeader[i];

for (let row = 0; row < H; row++) {
  const srcRow = H - 1 - row;                    // BMP stores rows bottom-up
  const rowStart = pixelOffset + row * rowSize;
  for (let x = 0; x < W; x++) {
    const [r, g, b] = pixels[srcRow][x];
    const p = rowStart + x * 3;
    buf[p] = b; buf[p + 1] = g; buf[p + 2] = r;   // BGR, not RGB
  }
}

const out = path.join(os.tmpdir(), "myjs-snapshot.bmp");
fs.writeFileSync(out, buf, "binary");
console.log(`Wrote   : ${out} (${buf.length} bytes)`);

open(out);   // the OS's real image viewer opens a file this script built byte by byte
