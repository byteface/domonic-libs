"""Scrape a JS-rendered page into structured data -- no browser.

    python examples/myjs/scrape.py

`myjs.Page` runs the page's <script>s against a real DOM, then you read it from
Python. Here the "page" builds its own content from a <script> (as a SPA would),
and we pull the rendered result out as JSON.
"""

import json
import myjs

SPA = """<!doctype html>
<html><head><title>Catalogue</title></head><body>
<main id="app">loading…</main>
<script>
  // Pretend this came from `fetch('/api/products')`.
  const products = [
    { id: 1, name: "Standing desk",  price: 429, tags: ["office", "ergonomic"], stock: 12 },
    { id: 2, name: "Mechanical keyboard", price: 119, tags: ["office", "typing"], stock: 0 },
    { id: 3, name: "Desk lamp",      price: 39,  tags: ["office", "lighting"], stock: 47 },
  ];
  const app = document.getElementById("app");
  app.innerHTML = products.map(p => `
    <article class="product" data-id="${p.id}" data-price="${p.price}">
      <h2>${p.name}</h2>
      <p class="tags">${p.tags.join(", ")}</p>
      <p class="stock ${p.stock ? "in" : "out"}">${p.stock ? p.stock + " in stock" : "sold out"}</p>
    </article>`).join("");
</script>
</body></html>"""


page = myjs.Page(SPA)

items = []
for art in page.query_all("article.product"):
    items.append({
        "id": int(art.getAttribute("data-id")),
        "name": art.querySelector("h2").textContent,
        "price": int(art.getAttribute("data-price")),
        "tags": art.querySelector(".tags").textContent.split(", "),
        "in_stock": "in" in (art.querySelector(".stock").getAttribute("class") or ""),
    })

print(f"scraped {len(items)} products from the rendered DOM:\n")
print(json.dumps(items, indent=2))

cheapest = min(items, key=lambda p: p["price"])
print(f"\ncheapest: {cheapest['name']} at ${cheapest['price']}")
