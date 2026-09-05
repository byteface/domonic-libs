// The real system clipboard -- no permission prompt, no browser sandbox.
//   myjs examples/myjs/clipboard.js   (then Cmd-V / Ctrl-V anywhere to check)

const report = `myjs report -- ${new Date().toString()}
cores: ${os.cpus().length}, host: ${os.hostname()}
generated entirely by a JavaScript file, no Node involved`;

clipboard.writeText(report);

console.log("Wrote the following to your REAL system clipboard:\n");
console.log(report);
console.log(`\nRead it straight back from the OS: ${clipboard.readText() === report ? "matches exactly" : "MISMATCH"}`);
console.log("\nPaste it (Cmd-V / Ctrl-V) into any app -- it'll still be there, this script doesn't undo it.");
