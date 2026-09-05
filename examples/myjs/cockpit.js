// A live, interactive control center -- every native trick in one script.
//   myjs examples/myjs/cockpit.js
//   keys: 1/2/3 kill a worker · r respawn all · c copy a report · q quit
//
// Ties together: a real-time OS dashboard (sysmon.js), real child processes
// you can kill and respawn with a single keypress and no Enter (procstream.js
// + raw terminal input, new here), a clipboard snapshot (clipboard.js), and
// a SIGINT handler that guarantees the terminal comes back sane even if you
// Ctrl-C out (signals.js). In a real terminal it's fully interactive; piped
// or non-interactive, it auto-cycles and exits on its own.

const mod = py.exec(`
import subprocess, threading, queue, sys, signal

try:
    import termios, tty
    _HAS_TERMIOS = True
except ImportError:
    _HAS_TERMIOS = False

def _has_tty():
    try:
        return _HAS_TERMIOS and sys.stdin.isatty()
    except Exception:
        return False

def _start_input():
    q = queue.Queue()
    if not _has_tty():
        return {"tty": False, "queue": q}
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    def reader():
        while True:
            ch = sys.stdin.read(1)
            if not ch:
                break
            q.put(ch)
    threading.Thread(target=reader, daemon=True).start()
    return {"tty": True, "queue": q, "fd": fd, "old": old}

def _stop_input(state):
    if state.get("tty"):
        termios.tcsetattr(state["fd"], termios.TCSADRAIN, state["old"])

def _poll_keys(state):
    out = []
    try:
        while True:
            out.append(state["queue"].get_nowait())
    except queue.Empty:
        pass
    return out

def _install_sigint_restore(state):
    # belt and braces: a Ctrl-C mid-demo must not leave the real terminal
    # stuck in cbreak mode -- restore it before Python's own default handler
    # would tear the process down.
    def handler(signum, frame):
        _stop_input(state)
        sys.stdout.write("\\r\\n(cockpit: Ctrl-C -- terminal restored)\\n")
        sys.exit(0)
    signal.signal(signal.SIGINT, handler)

def _spawn_worker():
    return subprocess.Popen(["sh", "-c", "while true; do sleep 0.5; done"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
`);

const hasTty = mod._has_tty();
const input = mod._start_input();
mod._install_sigint_restore(input);

const NAMES = ["alpha", "bravo", "charlie"];
let workers = [mod._spawn_worker(), mod._spawn_worker(), mod._spawn_worker()];

// -- reuse of sysmon.js's real OS readings ---------------------------------
function memoryPct() {
  if (os.platform() !== "darwin") return null;
  const out = sh("vm_stat").stdout;
  const page = (name) => Number(out.match(new RegExp(`${name}:\\s+(\\d+)`))[1]);
  const pageSize = Number(out.match(/page size of (\d+) bytes/)[1]);
  const available = page("Pages free") + page("Pages inactive") + page("Pages speculative");
  return 100 * (1 - (available * pageSize) / os.totalmem());
}

function diskPct() {
  const p = os.platform() === "win32" ? "C:\\" : "/";
  const cols = sh(`df -k "${p}"`).stdout.trim().split("\n").pop().split(/\s+/);
  return Number(cols[4].replace("%", ""));
}

function bar(pct, width = 20) {
  const filled = Math.max(0, Math.min(width, Math.round((pct / 100) * width)));
  return "#".repeat(filled) + "-".repeat(width - filled);
}

function report() {
  const alive = workers.filter((w) => w.poll() === null).length;
  return [
    `myjs cockpit report -- ${new Date().toString()}`,
    `host: ${os.hostname()} (${os.type()} ${os.release()})`,
    `cpu: ${os.cpus().length} cores  ·  mem: ${(memoryPct() ?? 0).toFixed(0)}%  ·  disk: ${diskPct()}%`,
    `workers: ${alive}/${workers.length} running`,
  ].join("\n");
}

function render(tick) {
  console.clear();
  console.log("myjs cockpit -- a live control center, all native");
  console.log("=".repeat(60));
  console.log(`Host    ${os.hostname()}  (${os.type()} ${os.release()})`);
  const mem = memoryPct();
  if (mem != null) console.log(`Memory  [${bar(mem)}] ${mem.toFixed(1)}%`);
  console.log(`Disk    [${bar(diskPct())}] ${diskPct()}%`);
  console.log("\nWorkers (this demo's own child processes -- safe to kill):");
  workers.forEach((w, i) => {
    const alive = w.poll() === null;
    console.log(`  [${i + 1}] ${NAMES[i].padEnd(8)} PID ${String(w.pid).padEnd(7)} ${alive ? "running" : "killed"}`);
  });
  console.log(
    hasTty
      ? "\nkeys: 1/2/3 kill a worker  ·  r respawn all  ·  c copy report  ·  q quit"
      : "\n(no interactive terminal -- auto-demo mode, will exit shortly)"
  );
}

let stopped = false;
function cleanup(reason) {
  if (stopped) return;
  stopped = true;
  clearInterval(id);
  for (const w of workers) if (w.poll() === null) w.kill();
  mod._stop_input(input);
  console.log(`\n(cockpit stopped -- ${reason}; workers killed, terminal restored)`);
}

let tick = 0;
const id = setInterval(() => {
  tick++;
  for (const key of mod._poll_keys(input)) {
    if (key === "q") return cleanup("quit");
    if (key === "c") {
      clipboard.writeText(report());
      console.log("\n[copied a live report to the system clipboard]");
    } else if (key === "r") {
      workers = workers.map((w, i) => (w.poll() === null ? w : mod._spawn_worker()));
    } else if (key >= "1" && key <= "3") {
      const w = workers[Number(key) - 1];
      if (w.poll() === null) w.kill();
    }
  }
  render(tick);
  if (!hasTty && tick >= 6) cleanup("no terminal to drive it");
  if (tick >= 120) cleanup("60s safety timeout");   // ~500ms per tick
}, 500);
