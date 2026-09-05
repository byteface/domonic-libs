# `dlx` -- the domonic-libs command line

Installing `domonic-libs` puts two console scripts on your `PATH`: `dlx` (short) and `domonic-libs` (the long alias). `python -m domonic_libs` runs the same thing without needing the scripts on `PATH`.

## Install

The tidiest way to get just the CLI, in its own isolated environment, is [pipx](https://pipx.pypa.io/):

```bash
pipx install domonic-libs
```

Upgrade or remove it later with `pipx upgrade domonic-libs` / `pipx uninstall domonic-libs`.

Run it once without installing anything permanent:

```bash
pipx run --spec domonic-libs dlx mermaid diagram.mmd
```

Or, in a project that already depends on `domonic-libs`, just `pip install` it and `dlx` is there.

## Conventions

* Every text command takes **one input**: a file path, or `-` / nothing for **stdin**.
* Output goes to `--output` / `-o`, or **stdout** by default. `-o -` also means stdout.
* Informational lines (`wrote ...`, `--stats`, `--report`) go to **stderr**, so piping stdout stays clean.
* Exit status: `0` success, `1` a check failed or nothing was produced, `2` a usage / input error.
* `dlx <command> -h` prints that command's options.

---

## `dlx mermaid` -- diagram text to SVG

```
dlx mermaid [INPUT] [-o FILE] [--type T] [--html] [--open] [--stats] [--list]
```

Renders Mermaid diagram text to an `<svg>`. The diagram type (`flowchart` / `graph`, `sequenceDiagram`, `pie`, `timeline`) is detected from the first line.

| flag | effect |
| --- | --- |
| `--type flowchart\|sequence\|pie\|timeline` | skip detection and force a type |
| `--html` | wrap the SVG in a minimal standalone HTML page |
| `--open` | render to a temp file and open it in the default browser |
| `--stats` | print node / edge / participant counts and the pixel size to stderr |
| `--list` | list the supported diagram types and exit |

```bash
dlx mermaid architecture.mmd -o architecture.svg
cat sequence.mmd | dlx mermaid --stats > sequence.svg
dlx mermaid flow.mmd --open
```

Flowcharts are laid out by the bundled `dagre` port; the others have dedicated renderers. See the main README for what each renderer covers.

---

## `dlx md` -- Markdown to HTML (marked)

```
dlx md [INPUT] [-o FILE] [--no-gfm] [--breaks] [--pedantic]
```

GitHub-flavoured Markdown is on by default (`--no-gfm` to disable). `--breaks` turns every single newline into `<br>`; `--pedantic` selects the original Markdown.pl quirks.

```bash
echo "# Notes\n\n- [x] done\n- [ ] todo" | dlx md
dlx md CHANGELOG.md -o changelog.html
```

---

## `dlx html2md` -- HTML to Markdown (turndown)

```
dlx html2md [INPUT] [-o FILE] [--gfm] [--heading-style atx|setext]
            [--code-block-style fenced|indented] [--bullet -|*|+]
```

`--gfm` enables the GFM plugin (tables, `~~strikethrough~~`, task lists).

```bash
dlx html2md email.html --gfm > email.md
curl -s https://example.com | dlx html2md
```

---

## `dlx read` -- extract the main article (readability)

```
dlx read (URL | FILE | -) [-o FILE] [--md] [--json]
```

Runs Mozilla Readability over a page and returns just the article. A `URL` argument is fetched (plain `urllib`, no extra dependency); anything else is read as HTML.

| flag | effect |
| --- | --- |
| *(default)* | the cleaned article HTML |
| `--md` | convert that article to Markdown (adds an `# H1` from the title) |
| `--json` | the article metadata (title, byline, excerpt, dates, ...) as JSON |

```bash
dlx read https://example.com/2024/some-post --md > post.md
dlx read saved-page.html --json | jq .title
```

Exit `1` if no article-like content is found.

---

## `dlx sanitize` -- clean hostile HTML (DOMPurify)

```
dlx sanitize [INPUT] [-o FILE] [--profile html|svg|mathml|all]
             [--allow-tags A,B] [--allow-attr A,B] [--strip-tags A,B] [--report]
```

`--profile` picks an allow-list profile (`all` = HTML + SVG + MathML, the default). `--allow-tags` / `--allow-attr` add to it; `--strip-tags` forbids. `--report` lists every removed node and attribute on stderr.

```bash
dlx sanitize user-comment.html --profile html --report
echo '<img src=x onerror=alert(1)>' | dlx sanitize
```

---

## `dlx validate` -- one-off validator.js checks

```
dlx validate [CHECK] [VALUE ...] [--list]
```

Runs a single check by name. Arguments after the value are passed through; anything that parses as a JSON literal (numbers, `true`, `{...}`) is decoded first, so options work:

```bash
dlx validate isEmail ada@example.com            # -> true   (exit 0)
dlx validate isEmail nope                        # -> false  (exit 1)
dlx validate isIBAN DE89370400440532013000
dlx validate isLength "abcd" '{"min": 2, "max": 8}'
dlx validate normalizeEmail "Ada.Lovelace+news@Gmail.com"
dlx validate --list                              # every check name
```

Boolean checks set the exit status (`0` true / `1` false); sanitizers and converters just print their result.

---

## `dlx qs` -- query strings

```
dlx qs parse "QUERY_STRING" [-o FILE] [--depth N]
dlx qs stringify 'JSON_OBJECT' [-o FILE]
```

`parse` turns a query string into JSON (nested keys, `key[]` arrays, dot notation up to `--depth`, default 5). `stringify` does the reverse from a JSON object.

```bash
dlx qs parse "filter[status]=open&filter[tags][]=bug&page=2"
dlx qs stringify '{"filter": {"status": "open"}, "page": 2}'
```

---

## `dlx minify` / `dlx fmt` -- JavaScript, pure Python

```
dlx minify [INPUT] [-o FILE] [--module]
dlx fmt    [INPUT] [-o FILE] [--module] [--indent N]
```

Parses JavaScript with the `acorn` port and regenerates it from the AST --
`minify` strips every optional space, newline and comment; `fmt` re-emits it
with consistent `--indent` (default 2). No Node, no `terser`, no build step.
It's not a mangler (identifiers keep their names) -- the win is whitespace and
comment removal, which is most of what a source-map-free minify buys you, plus
a dependable formatter.

```bash
dlx minify src/app.js -o dist/app.min.js     # "... 41231 -> 18004 bytes (56% smaller)" on stderr
cat messy.js | dlx fmt --indent 4
```

`parse -> generate` round-trips: the regenerated program parses back to an
equivalent tree. Verified against the js262 + conformance corpus and real
bundles (lodash, d3, vue, react, jquery, moment, ...).

---

## `dlx dagre` -- lay out and draw a graph

```
dlx dagre [INPUT] [-o FILE] [--rankdir tb|bt|lr|rl] [--open]
```

Takes a plain edge list -- one `a -> b` (or `a b`) per line, `# some text` after a `#` becomes an edge label, bare words are lone nodes, `//` and leading `#` start comments -- runs it through the `dagre` layout port, and emits a simple SVG.

```bash
printf 'client -> api\napi -> db\napi -> cache\ncache -> db\n' \
  | dlx dagre --rankdir LR --open
```

This is a thin wrapper; for real diagrams use `dlx mermaid` with a `flowchart`.
