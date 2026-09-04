// ===================================================================
//  This is JavaScript. There is no Node. It is running inside Python.
//  Run it:   myjs examples/myjs_wow.js
// ===================================================================

// --- 1. it knows your actual machine --------------------------------
console.log(`Host    : ${os.type()} ${os.arch()}  (${os.cpus().length} cores, ${(os.totalmem() / 1e9).toFixed(0)} GB)`);
console.log(`CPU     : ${os.cpus()[0].model}`);
console.log(`You     : ${os.userInfo().username} @ ${os.hostname()}`);

// --- 2. it can run shell commands ----------------------------------
const branch = sh("git rev-parse --abbrev-ref HEAD 2>/dev/null || echo n/a").trim();
console.log(`Git     : on branch ${branch}`);

// --- 3. it can read your files ------------------------------------
const here = fs.readdirSync(".").filter(n => !n.startsWith("."));
console.log(`Folder  : ${here.length} things here -> ${here.slice(0, 4).join(", ")}, ...`);

// --- 4. it can reach the whole Python ecosystem -----------------
const stats = py.import("statistics");
const sample = py.import("random").sample([...Array(50).keys()], 10);
console.log(`Python  : mean of ${sample.join(",")} = ${stats.mean(sample)}`);

// --- 5. it can pull live data off the internet ----------------
const repo = fetchSync("https://api.github.com/repos/byteface/domonic").json();
console.log(`Live    : domonic has ${repo.stargazers_count} stars, last pushed ${repo.pushed_at}`);

// --- 6. it can call straight into native C --------------------
const libm = ffi.loadLibrary("m");
libm.tgamma.argtypes = [ffi.types.double];
libm.tgamma.restype = ffi.types.double;
console.log(`C       : 10! via libm tgamma(11) = ${libm.tgamma(11)}`);

// --- 7. it has a real DOM, and can write the page to disk -----
const page = document.createElement("html");
const body = document.createElement("body");
const h1 = document.createElement("h1");
h1.textContent = "Generated entirely from JavaScript";
const p = document.createElement("p");
p.textContent = `Built on ${os.type()} at ${new Date().toISOString?.() ?? Date.now()}`;
body.appendChild(h1);
body.appendChild(p);
page.appendChild(body);

const out = path.join(os.tmpdir(), "myjs-wow.html");
fs.writeFileSync(out, "<!doctype html>\n" + String(page));
console.log(`Wrote   : ${out}`);

// --- 8. ...and it can make your computer react -----------------
notify("Demo finished — open the file it just wrote", "myjs");
// say("the demo is complete");        // uncomment for audio
// open(out);                          // uncomment to open the page in your browser

console.log("\ndone. (uncomment the last two lines for the full effect)");
