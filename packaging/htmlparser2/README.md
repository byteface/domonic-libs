# htmlparser2

A faithful-shape Python port of [`fb55/htmlparser2`](https://github.com/fb55/htmlparser2),
backed by domonic DOM nodes.

```bash
pip install htmlparser2
htmlparser2 page.html --stats
cat page.html | htmlparser2 --text
```

```python
from htmlparser2 import DomUtils, parseDocument

doc = parseDocument("<ul><li>One<li>Two</ul>")
print(DomUtils.textContent(doc))
```

It can also register itself as a domonic parser backend:

```python
from domonic import domonic
from htmlparser2 import install_domonic_parser

install_domonic_parser()
page = domonic.parseString("<main><h1>Hello</h1></main>", parser="htmlparser2")
```

This package is built from the same repository as `domonic-libs`, but ships as
its own top-level import so the umbrella package does not own the parser source.
