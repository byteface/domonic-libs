// A real CLI tool written in JavaScript.
//
//   myjs examples/myjs/todo.js add "buy milk"
//   myjs examples/myjs/todo.js add "write the docs"
//   myjs examples/myjs/todo.js list
//   myjs examples/myjs/todo.js done 1
//   myjs examples/myjs/todo.js clear
//
// Persists to ~/.myjs-todos.json with `fs`; reads `argv`; prints a table.

const FILE = path.join(os.homedir(), ".myjs-todos.json");

const load = () => (fs.existsSync(FILE) ? JSON.parse(fs.readFileSync(FILE)) : []);
const save = (todos) => fs.writeFileSync(FILE, JSON.stringify(todos, null, 2));

const [cmd, ...rest] = argv;
const todos = load();

switch (cmd) {
  case "add": {
    todos.push({ text: rest.join(" "), done: false, at: new Date().toISOString().slice(0, 10) });
    save(todos);
    console.log(`added #${todos.length}: ${todos[todos.length - 1].text}`);
    break;
  }
  case "done": {
    const i = Number(rest[0]) - 1;
    if (!todos[i]) { console.error(`no todo #${rest[0]}`); process.exit(1); }
    todos[i].done = true;
    save(todos);
    console.log(`✓ ${todos[i].text}`);
    break;
  }
  case "clear": {
    save(todos.filter((t) => !t.done));
    console.log("cleared completed todos");
    break;
  }
  case "list":
  case undefined: {
    if (!todos.length) { console.log("nothing to do 🎉"); break; }
    console.table(todos.map((t, i) => ({
      "#": i + 1,
      "": t.done ? "✓" : " ",
      task: t.text,
      added: t.at,
    })));
    const open = todos.filter((t) => !t.done).length;
    console.log(`${open} open · ${todos.length - open} done`);
    break;
  }
  default:
    console.error(`unknown command: ${cmd}\nusage: todo [add <text> | list | done <n> | clear]`);
    process.exit(1);
}
