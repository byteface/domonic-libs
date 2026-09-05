// Real process control: spawn a child process, stream its output, kill it early.
//   myjs examples/myjs/procstream.js

const mod = py.exec(`
import subprocess, threading, queue

def _spawn_streaming(cmd):
    q = queue.Queue()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    def pump():
        for line in proc.stdout:
            q.put(line.rstrip("\\n"))
        q.put(None)   # sentinel: the process's stdout closed on its own
    threading.Thread(target=pump, daemon=True).start()
    return {"queue": q, "proc": proc}

def _poll(state):
    out = []
    try:
        while True:
            out.append(state["queue"].get_nowait())
    except queue.Empty:
        pass
    return out

def _kill(state):
    state["proc"].kill()

def _pid(state):
    return state["proc"].pid
`);

const cmd = ["sh", "-c", "for i in $(seq 1 20); do echo \"tick $i\"; sleep 0.3; done"];
const state = mod._spawn_streaming(cmd);
console.log(`Spawned PID ${mod._pid(state)}, scheduled to print 20 lines over 6s.`);
console.log("Watching for 2s, then killing it early:\n");

let seen = 0;
const id = setInterval(() => {
  for (const line of mod._poll(state)) {
    if (line === null) {
      clearInterval(id);
      console.log("\n(process finished on its own)");
      return;
    }
    console.log("  " + line);
    seen++;
  }
}, 150);

setTimeout(() => {
  clearInterval(id);
  mod._kill(state);
  console.log(`\nKilled PID ${mod._pid(state)} after ${seen} of the 20 lines -- real signal, real process.`);
}, 2000);
