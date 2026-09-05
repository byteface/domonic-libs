// Real async/await, Promises, and a working event loop.
//   myjs examples/myjs/async.js

// --- timers and microtask ordering (like a browser) -----------------
console.log("1  sync");
setTimeout(() => console.log("4  setTimeout(0)"), 0);
Promise.resolve().then(() => console.log("3  microtask"));
console.log("2  sync");

// --- async/await over a promised timer ---------------------------
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function countdown(n) {
  while (n > 0) {
    console.log(`   T-minus ${n}`);
    await wait(120);
    n--;
  }
  console.log("   liftoff");
}

// --- concurrent HTTP: three requests, in parallel, from JS ---------
async function main() {
  await countdown(3);

  const t = Date.now();
  const users = ["torvalds", "gvanrossum", "byteface"];
  const people = await Promise.all(
    users.map(async (u) => {
      const r = await fetch(`https://api.github.com/users/${u}`);
      const j = r.json();
      return `${j.name || u} — ${j.public_repos} repos, ${j.followers} followers`;
    })
  );
  console.log(`\nfetched ${people.length} GitHub profiles in ${((Date.now() - t) / 1000).toFixed(1)}s (concurrently):`);
  people.forEach((p) => console.log("  •", p));

  // Promise.race — whichever endpoint answers first wins
  const fastest = await Promise.race([
    fetch("https://api.github.com/zen").then((r) => "github: " + r.text()),
    fetch("https://www.boredapi.com/api/activity").then((r) => "boredapi: " + r.json().activity),
  ]);
  console.log("\nrace winner:", fastest);
}

main().then(() => console.log("\ndone."));
