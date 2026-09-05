// Build a UI with the DOM API; --gui shows it in a native window.
//   myjs --gui examples/myjs/gui.js

document.title = "myjs · system report";

const style = document.createElement("style");
style.textContent = `
  body { font: 15px/1.6 system-ui, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }
  header { padding: 2rem; background: linear-gradient(135deg, #1e293b, #0f172a); }
  h1 { margin: 0; font-size: 1.6rem; }
  .sub { color: #94a3b8; }
  table { width: 100%; border-collapse: collapse; }
  td { padding: .6rem 2rem; border-bottom: 1px solid #1e293b; }
  td:first-child { color: #94a3b8; width: 12rem; }
  code { color: #7dd3fc; }
`;
document.head.appendChild(style);

const header = document.createElement("header");
const h1 = document.createElement("h1");
h1.textContent = "System report";
const sub = document.createElement("p");
sub.className = "sub";
sub.textContent = "assembled entirely in JavaScript, rendered in a native window";
header.appendChild(h1);
header.appendChild(sub);
document.body.appendChild(header);

const rows = [
  ["OS", `${os.type()} ${os.release()} (${os.arch()})`],
  ["CPU", `${os.cpus()[0].model} × ${os.cpus().length}`],
  ["Memory", `${(os.totalmem() / 1e9).toFixed(1)} GB`],
  ["Host", `${os.userInfo().username}@${os.hostname()}`],
  ["Python", os.python],
  ["Shell", sh("echo $SHELL").trim()],
  ["cwd files", String(fs.readdirSync(".").length)],
];

const table = document.createElement("table");
for (const [k, v] of rows) {
  const tr = document.createElement("tr");
  const a = document.createElement("td"); a.textContent = k;
  const b = document.createElement("td");
  const c = document.createElement("code"); c.textContent = v;
  b.appendChild(c);
  tr.appendChild(a); tr.appendChild(b);
  table.appendChild(tr);
}
document.body.appendChild(table);

console.log("built a", rows.length, "row report; run with --gui to see it in a window");
