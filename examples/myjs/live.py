"""Hit a real, live website -- fetch its HTML, its CSS, and its JS, and run it.

    python examples/myjs/live.py
    python examples/myjs/live.py https://example.com

`myjs.Page.load(url)` fetches the page over HTTP, folds every
`<link rel="stylesheet">` into the document (so `getComputedStyle` sees the
real rules), fetches each `<script src>` -- resolving both relative to the
page URL -- and runs the scripts against a real DOM. No browser, no headless
Chromium: a `pip install`.
"""

import sys
import myjs

url = sys.argv[1] if len(sys.argv) > 1 else "https://byteface.github.io/"

print(f"fetching {url} ...\n")
page = myjs.Page.load(url)

print(f"  title        {page.title!r}")
print(f"  stylesheets  {page.eval('document.styleSheets.length')} "
      f"({page.count('link[rel=stylesheet]')} <link> + inline <style>)")
print(f"  scripts      {page.count('script')}")
print(f"  elements     {page.eval('document.getElementsByTagName(\"*\").length')}")

if page.errors:
    print(f"\n  {len(page.errors)} script error(s) (the site's own JS, running for real):")
    for e in page.errors[:4]:
        print(f"    - {str(e).splitlines()[0]}")

# the CSS genuinely applied -- these values come from the fetched stylesheet,
# resolved through domonic's CSSOM cascade, not from any inline style="".
print("\n  computed style, straight off the fetched CSS:")
for sel in ("body", "canvas", "h1", "a", "#ui", "p"):
    el = page.query(sel)
    if el is None:
        continue
    cs = f"getComputedStyle(document.querySelector({sel!r}))"
    bits = []
    for prop in ("color", "backgroundColor", "display", "position", "fontFamily"):
        val = page.eval(f"{cs}.{prop}")
        if val and val not in ("none", ""):
            bits.append(f"{prop}={val}")
    if bits:
        print(f"    {sel:10} {'  '.join(bits)}")

# and the DOM is real and queryable, post-scripts
links = page.query_all("a[href]")
print(f"\n  {len(links)} links on the page"
      + (f", first: {links[0].getAttribute('href')}" if links else ""))
