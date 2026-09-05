// Real OS threads, not an event-loop illusion -- hash buffers on every core.
//   myjs examples/myjs/parallel.js

const N = os.cpus().length;
const MB = 40;

console.log(`${N} cores available. Hashing ${N} x ${MB} MB buffers with SHA-256...\n`);

// The parallel section has to be real Python -- OS threads calling back into
// this interpreter from outside its one call stack isn't safe, so Python
// does its own timing internally and hands JS the finished numbers.
const mod = py.exec(`
import threading, hashlib, os, time

def _parallel_hash(n, size_mb):
    bufs = [os.urandom(size_mb * 1_000_000) for _ in range(n)]

    t0 = time.perf_counter()
    seq = [hashlib.sha256(b).hexdigest()[:8] for b in bufs]
    t1 = time.perf_counter()

    out = [None] * n
    def work(i):
        out[i] = hashlib.sha256(bufs[i]).hexdigest()[:8]
    threads = [threading.Thread(target=work, args=(i,)) for i in range(n)]
    t2 = time.perf_counter()
    for t in threads: t.start()
    for t in threads: t.join()
    t3 = time.perf_counter()

    return {"seq_ms": (t1 - t0) * 1000, "par_ms": (t3 - t2) * 1000, "seq": seq, "par": out}
`);

const r = mod._parallel_hash(N, MB);
const ok = r.seq.every((h, i) => h === r.par[i]);

console.log(`sequential  ${r.seq_ms.toFixed(1)} ms   [${[...r.seq].slice(0, 3).join(", ")}, ...]`);
console.log(`${N} threads  ${r.par_ms.toFixed(1)} ms   [${[...r.par].slice(0, 3).join(", ")}, ...]`);
console.log(`\n${(r.seq_ms / r.par_ms).toFixed(2)}x faster, same results (${ok ? "verified" : "MISMATCH"}).`);
console.log("Node's JS engine can't do this without a native worker_threads addon -- myjs gets it from Python for free.");
