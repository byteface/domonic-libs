// A native process table: ps(1)'s real numbers, parsed and sorted in JS.
//   myjs examples/myjs/procs.js

const lines = sh("ps -Ao pid,pcpu,rss,comm").stdout.trim().split("\n").slice(1);
const rows = lines.map((line) => {
  const m = line.trim().match(/^(\d+)\s+([\d.]+)\s+(\d+)\s+(.*)$/);
  return { pid: Number(m[1]), cpu: Number(m[2]), rssMb: Number(m[3]) / 1024, name: m[4].split("/").pop() };
});

rows.sort((a, b) => b.rssMb - a.rssMb);

console.log(`${rows.length} processes on this machine right now. Top 10 by memory:\n`);
console.table(rows.slice(0, 10).map((r) => ({
  PID: r.pid,
  "MEM (MB)": r.rssMb.toFixed(1),
  "CPU %": r.cpu.toFixed(1),
  NAME: r.name,
})));

const totalGb = rows.reduce((sum, r) => sum + r.rssMb, 0) / 1024;
console.log(`\nTotal RSS across every process: ${totalGb.toFixed(1)} GB`);

const mine = rows.find((r) => r.pid === process.pid);
if (mine) console.log(`This script itself: PID ${mine.pid}, ${mine.rssMb.toFixed(1)} MB resident`);
