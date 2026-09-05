// A directory watcher with no chokidar -- just fs + setInterval polling mtimes.
//   myjs examples/myjs/filewatch.js

const dir = path.join(os.tmpdir(), "myjs-filewatch-demo");
fs.rmSync?.(dir, { recursive: true, force: true });
fs.mkdirSync(dir, { recursive: true });

function snapshot() {
  const out = new Map();
  for (const name of fs.readdirSync(dir)) {
    out.set(name, fs.statSync(path.join(dir, name)).mtimeMs);
  }
  return out;
}

let prev = snapshot();
console.log(`Watching ${dir} ...\n`);

// simulate an editor: a real OS thread writes/edits/removes files on its own
// schedule while the JS timer above polls independently -- two real
// concurrent actors, not one script pretending to be two
const mod = py.exec(`
import threading, time, os

def _simulate(d):
    def run():
        time.sleep(0.3); open(os.path.join(d, "draft.txt"), "w").write("v1")
        time.sleep(0.3); open(os.path.join(d, "notes.txt"), "w").write("hello")
        time.sleep(0.3); open(os.path.join(d, "draft.txt"), "w").write("v2")
        time.sleep(0.3); os.remove(os.path.join(d, "notes.txt"))
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t
`);
mod._simulate(dir);

const id = setInterval(() => {
  const cur = snapshot();
  for (const [name, mtime] of cur) {
    if (!prev.has(name)) console.log(`+ created   ${name}`);
    else if (prev.get(name) !== mtime) console.log(`~ modified  ${name}`);
  }
  for (const name of prev.keys()) {
    if (!cur.has(name)) console.log(`- removed   ${name}`);
  }
  prev = cur;
}, 100);

setTimeout(() => {
  clearInterval(id);
  fs.rmSync?.(dir, { recursive: true, force: true });
  console.log("\n(watch stopped, scratch dir cleaned up)");
}, 1800);
