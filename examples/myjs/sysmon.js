// A live CPU / memory / disk / battery dashboard, straight from the real OS.
//   myjs examples/myjs/sysmon.js   (auto-stops after 5 ticks here)

function bar(pct, width = 24) {
  const filled = Math.max(0, Math.min(width, Math.round((pct / 100) * width)));
  return "#".repeat(filled) + "-".repeat(width - filled);
}

function gb(bytes) {
  return (bytes / 1e9).toFixed(1) + " GB";
}

// memory pressure straight out of `vm_stat` (darwin) -- free + inactive +
// speculative pages are all reclaimable, so that's "available", same
// definition Activity Monitor uses (there's no portable syscall for this)
function memoryPct() {
  if (os.platform() !== "darwin") return null;
  const out = sh("vm_stat").stdout;
  const page = (name) => Number(out.match(new RegExp(`${name}:\\s+(\\d+)`))[1]);
  const pageSize = Number(out.match(/page size of (\d+) bytes/)[1]);
  const available = page("Pages free") + page("Pages inactive") + page("Pages speculative");
  const total = os.totalmem();
  return 100 * (1 - (available * pageSize) / total);
}

// disk usage via `df` -- one line of shell beats writing a cross-platform
// statvfs wrapper, and it's the same numbers `df -h` shows you
function disk() {
  const path = os.platform() === "win32" ? "C:\\" : "/";
  const line = sh(`df -k "${path}"`).stdout.trim().split("\n").pop();
  const cols = line.split(/\s+/);
  return { usedKb: Number(cols[2]), totalKb: Number(cols[1]), pct: Number(cols[4].replace("%", "")) };
}

function battery() {
  if (os.platform() !== "darwin") return null;
  const out = sh("pmset -g batt").stdout;
  const m = out.match(/(\d+)%/);
  const charging = /AC Power/.test(out) && !/discharging/.test(out);
  return m ? { pct: Number(m[1]), charging } : null;
}

let tick = 0;

function render() {
  const d = disk();
  const memPct = memoryPct();
  const cpus = os.cpus();
  const batt = battery();

  console.clear();
  console.log(`myjs sysmon  --  ${os.type()} ${os.release()}  (tick ${++tick})`);
  console.log("=".repeat(58));
  console.log(`Host    ${os.hostname()}`);
  console.log(`CPU     ${cpus[0].model}  x${cpus.length}`);
  if (memPct != null) {
    console.log(`Memory  [${bar(memPct)}] ${memPct.toFixed(1)}%  of ${gb(os.totalmem())}`);
  } else {
    console.log(`Memory  total ${gb(os.totalmem())}`);
  }
  console.log(`Disk    [${bar(d.pct)}] ${d.pct}%  ${gb(d.usedKb * 1024)} / ${gb(d.totalKb * 1024)}`);
  if (batt) {
    console.log(`Battery [${bar(batt.pct)}] ${batt.pct}%  ${batt.charging ? "charging" : "on battery"}`);
  }
  console.log(`Uptime  ${(os.uptime() / 3600).toFixed(1)}h  ·  PID ${process.pid}  ·  ${process.platform}/${process.arch}`);
}

render();
const id = setInterval(render, 1000);
setTimeout(() => { clearInterval(id); console.log("\n(sysmon stopped)"); }, 5000);
