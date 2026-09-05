// A real Flask app -- route handlers written as plain JS functions.
//   myjs examples/myjs/flask.js   (needs Flask: pip install flask)

const flask = py.import("flask");
const app = flask.Flask("myjs");

function index() {
  return `<h1>Hello from JavaScript</h1><p>Served by real Flask at ${new Date().toString()}</p>`;
}
app.add_url_rule("/", "index", index);

function api() {
  return flask.jsonify({ from_: "JavaScript", cores: os.cpus().length, engine: "myjs on Flask" });
}
app.add_url_rule("/api", "api", api);

// run Flask's real dev server on a background thread so this script can
// also hit it and prove the round trip, then keep it alive for you to try
const mod = py.exec(`
import threading
def _serve(app, port):
    t = threading.Thread(target=lambda: app.run(port=port, debug=False, use_reloader=False), daemon=True)
    t.start()
    return t
`);
const PORT = 5099;
const server = mod._serve(app, PORT);
sleep(0.6);

const r1 = fetchSync(`http://127.0.0.1:${PORT}/`);
console.log(`GET /     -> ${r1.status}  ${r1.text().slice(0, 60)}...`);

const r2 = fetchSync(`http://127.0.0.1:${PORT}/api`);
console.log(`GET /api  -> ${r2.status}  ${r2.text()}`);

console.log(`\nStill running at http://127.0.0.1:${PORT}/ -- open it in a browser. Ctrl-C to stop.`);
server.join();
