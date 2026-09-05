// Real POSIX signals: spawn a child, send it SIGTERM, watch it trap and exit.
//   myjs examples/myjs/signals.js

const mod = py.exec(`
import subprocess, signal, sys, time

_CHILD_SRC = """
import signal, sys, time
def handler(signum, frame):
    print(f"child: caught signal {signum} ({signal.Signals(signum).name}) -- cleaning up", flush=True)
    sys.exit(0)
signal.signal(signal.SIGTERM, handler)
print("child: ready, working...", flush=True)
for i in range(20):
    time.sleep(0.3)
print("child: finished naturally (should not print)", flush=True)
"""

def _spawn_child():
    return subprocess.Popen([sys.executable, "-c", _CHILD_SRC], stdout=subprocess.PIPE, text=True, bufsize=1)

def _readline(proc):
    return proc.stdout.readline().rstrip("\\n")

def _terminate(proc):
    proc.send_signal(signal.SIGTERM)

def _wait(proc):
    return proc.wait()
`);

const child = mod._spawn_child();
console.log(mod._readline(child));

console.log("Parent (myjs): letting it run for 800ms, then sending real SIGTERM...\n");
sleep(0.8);

mod._terminate(child);
console.log(mod._readline(child));

const code = mod._wait(child);
console.log(`\nChild exited with code ${code} -- it chose to exit(0) itself, from inside its own signal handler.`);
