// Real audio: synthesized with JS math, packed to PCM16 bytes, OS-played.
//   myjs examples/myjs/wav.js

const SR = 44100;                                  // sample rate, Hz
const NOTES = [261.63, 329.63, 392.0, 523.25];      // C4 E4 G4 C5
const DUR = 0.25;                                   // seconds per note

// pure JS math: one amplitude (-1..1) per sample, a sine wave per note with
// a half-sine envelope so notes don't click at the edges
const samples = [];
for (const freq of NOTES) {
  const n = Math.round(SR * DUR);
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    const envelope = Math.sin((Math.PI * i) / n);
    samples.push(Math.sin(2 * Math.PI * freq * t) * envelope * 0.8);
  }
}
console.log(`${samples.length} samples of JS math -> a real .wav file`);

// hand the raw amplitudes to Python to pack real 16-bit PCM frames -- `wave`
// writes a byte-perfect WAV header, `struct` does the sample packing
const mod = py.exec(`
import wave, struct, io

def _make_wav(amps, sr):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, a)) * 32767)) for a in amps))
    return buf.getvalue()
`);

const wavBytes = mod._make_wav(samples, SR);
const out = path.join(os.tmpdir(), "myjs-tune.wav");
fs.writeFileSync(out, wavBytes, "binary");
console.log(`Wrote ${out} (${wavBytes.length} bytes)`);

open(out);   // hands off to the OS's real default audio player, no GUI code here at all
