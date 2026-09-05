// The DOM is a graphics API: build an SVG bar chart, write it, open it.
//   myjs examples/myjs/chart.js

const data = [
  { label: "Mon", value: 42 },
  { label: "Tue", value: 88 },
  { label: "Wed", value: 61 },
  { label: "Thu", value: 95 },
  { label: "Fri", value: 73 },
];

const W = 480, H = 260, PAD = 32;
const max = Math.max(...data.map((d) => d.value));
const bw = (W - PAD * 2) / data.length;

const svg = document.createElement("svg");
svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
svg.setAttribute("width", W);
svg.setAttribute("height", H);

function add(tag, attrs, text) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (text != null) el.textContent = text;
  svg.appendChild(el);
  return el;
}

add("rect", { x: 0, y: 0, width: W, height: H, fill: "#0f172a" });

data.forEach((d, i) => {
  const h = (d.value / max) * (H - PAD * 2);
  const x = PAD + i * bw + bw * 0.15;
  const y = H - PAD - h;
  add("rect", { x, y, width: bw * 0.7, height: h, fill: "#38bdf8", rx: 3 });
  add("text", { x: x + bw * 0.35, y: y - 6, fill: "#e2e8f0", "font-size": 12,
                "text-anchor": "middle", "font-family": "system-ui" }, d.value);
  add("text", { x: x + bw * 0.35, y: H - PAD + 16, fill: "#94a3b8", "font-size": 12,
                "text-anchor": "middle", "font-family": "system-ui" }, d.label);
});

const out = path.join(os.tmpdir(), "myjs-chart.svg");
fs.writeFileSync(out, `<?xml version="1.0"?>\n${svg.outerHTML}`);
console.log("wrote", out);
// open(out);   // uncomment to view it
