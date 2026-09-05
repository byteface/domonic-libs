// The OS's own UI from JavaScript: notify, alert, prompt, confirm, file pickers.
//   myjs examples/myjs/dialogs.js   (macOS; falls back to stdin elsewhere)

notify("myjs is running this script", "dialogs.js");

const name = prompt("What should I call you?", "friend");
console.log(`prompt()  -> ${JSON.stringify(name)}`);

const proceed = confirm(`Nice to meet you, ${name}. Continue to the file picker?`);
console.log(`confirm() -> ${proceed}`);

if (proceed) {
  const file = chooseFile();
  console.log(`chooseFile()   -> ${file ?? "(cancelled)"}`);
  if (file) {
    const stat = fs.statSync(file);
    alert(`${path.basename(file)} is ${stat.size} bytes`);
  }

  const folder = chooseFolder();
  console.log(`chooseFolder() -> ${folder ?? "(cancelled)"}`);
}

say(`Goodbye, ${name}`);
console.log("\ndone -- every dialog above was the real macOS UI, not a web <input>.");
