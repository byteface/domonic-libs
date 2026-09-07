"""Use htmlparser2 as a domonic parser backend.

Run:
    python examples/htmlparser2_backend.py
    echo '<main><h1>Hi</h1><p>There</p></main>' | python -m domonic_libs htmlparse --stats
"""

from domonic import domonic
from htmlparser2 import DomUtils, install_domonic_parser, parseDocument


HTML = """
<!doctype html>
<main>
  <h1>htmlparser2 backend</h1>
  <p class="lead">A fast parser path that builds domonic nodes directly.</p>
  <ul><li>One<li>Two<li>Three</ul>
</main>
"""


doc = parseDocument(HTML)
items = DomUtils.getElementsByTagName("li", doc)
print(f"parseDocument li count: {len(items)}")
print(f"text: {DomUtils.textContent(doc).strip()}")

install_domonic_parser()
page = domonic.parseString(HTML, parser="htmlparser2")
print(f"domonic active parser: {domonic.get_active_parser()}")
print(f"h1: {page.querySelector('h1').textContent}")
