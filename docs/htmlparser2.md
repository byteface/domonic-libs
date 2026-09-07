# htmlparser2

`htmlparser2` is a standalone top-level package built from `src/htmlparser2/`
via `packaging/htmlparser2/`.

```bash
pip install htmlparser2
htmlparser2 page.html --stats
cat page.html | htmlparser2 --text
```

```python
from htmlparser2 import DomUtils, Parser, parseDocument

events = []
Parser({
    "onopentag": lambda name, attrs, implied: events.append((name, attrs)),
    "ontext": lambda text: events.append(text),
}).end('<p class="lead">Hello &amp; welcome</p>')

doc = parseDocument("<ul><li>One<li>Two</ul>")
items = DomUtils.getElementsByTagName("li", doc)
```

The port keeps the upstream htmlparser2 shape: callback parser, tokenizer state
machine, `DomHandler`, `DomUtils`, feed helpers, implied-close rules, void
elements, raw-text / RCDATA / plaintext parsing, and SVG/MathML casing tables.
It builds domonic nodes directly.

It can also patch itself into domonic for a process:

```python
from domonic import domonic
from htmlparser2 import install_domonic_parser

install_domonic_parser()
page = domonic.parseString("<main><h1>Hello</h1></main>", parser="htmlparser2")
```

Benchmark against domonic's parser backends:

```bash
python scripts/benchmark_htmlparser2.py path/to/page.html --iterations 3
```
