// Read a real binary file header with `struct` -- no image library needed.
//   myjs examples/myjs/bmp.js [path-to-a.bmp]   (writes a sample if none given)

const target = (typeof argv !== "undefined" && argv[0]) || path.join(os.tmpdir(), "myjs-sample.bmp");

if (!fs.existsSync(target)) {
  // hand-pack a minimal, valid BMP: a 14-byte file header + 40-byte
  // BITMAPINFOHEADER + a few solid-color rows, padded to a 4-byte boundary
  // per the spec -- Python does the exact byte-packing, `struct` does the header
  const mod = py.exec(`
import struct

def _make_bmp(w, h):
    row_size = (w * 3 + 3) // 4 * 4
    row = bytes([0, 128, 255] * w).ljust(row_size, b"\\0")   # BGR: an orange stripe
    pixels = row * h
    pixel_offset = 14 + 40
    file_header = struct.pack("<2sIHHI", b"BM", pixel_offset + len(pixels), 0, 0, pixel_offset)
    dib_header = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)
    return file_header + dib_header + pixels
`);
  fs.writeFileSync(target, mod._make_bmp(4, 3), "binary");
  console.log(`(wrote a sample BMP to ${target} -- run again with a real path to inspect that instead)\n`);
}

// --- the actual header read ------------------------------------------------
// BMP layout: a 14-byte file header, then a 40-byte BITMAPINFOHEADER (the
// common case -- newer/larger DIB headers exist but start the same way).
const header = fs.readBytes(target, 54);

const [sig, fileSize, r1, r2, pixelOffset] = struct.unpack_from("<2sIHHI", header);
const [dibSize, width, height, planes, bpp, compression, imageSize] =
  struct.unpack_from("<IiiHHII", header, 14);

console.log(`File     : ${target}`);
console.log(`Format   : ${sig.decode("ascii")}`);
console.log(`Size     : ${(fileSize / 1024).toFixed(2)} KB`);
console.log(`Pixels @ : byte offset ${pixelOffset}`);
console.log(`DIB size : ${dibSize} bytes`);
console.log(`Width    : ${width}px`);
console.log(`Height   : ${Math.abs(height)}px${height > 0 ? " (bottom-up)" : " (top-down)"}`);
console.log(`Depth    : ${bpp}-bit, ${planes} plane(s)`);
console.log(`Compress : ${compression === 0 ? "none (BI_RGB)" : compression}`);
