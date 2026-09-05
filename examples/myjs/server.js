// A web server in JavaScript, no Node -- HTML built with document.createElement.
//   myjs examples/myjs/server.js   (then open http://127.0.0.1:8080, Ctrl-C to stop)

let hits = 0;

http.serve(8080, (req) => {
  hits++;

  if (req.path === "/api/host") {
    return {
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        os: os.type(),
        arch: os.arch(),
        cores: os.cpus().length,
        hits: hits,
      }),
    };
  }

  // build the page with document.createElement -- server-side DOM
  const page = document.createElement("main");
  const h1 = document.createElement("h1");
  h1.textContent = "Served from JavaScript";
  const info = document.createElement("p");
  info.textContent = `${req.method} ${req.path} - request #${hits} - ${os.type()} ${os.arch()}`;
  const quote = document.createElement("blockquote");
  quote.textContent = fetchSync("https://api.github.com/zen").text();

  page.appendChild(h1);
  page.appendChild(info);
  page.appendChild(quote);

  return "<!doctype html><meta charset=utf-8><style>body{font:16px/1.6 system-ui;max-width:40rem;margin:4rem auto}</style>" + String(page);
});
