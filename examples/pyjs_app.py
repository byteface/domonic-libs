"""Write an interactive web app in Python -> one self-contained HTML file.

    python examples/pyjs_app.py

The app logic below is real Python. `domonic_libs.pyjs` transpiles it to
JavaScript, this script drops it into a single ``.html`` file (styles + markup
+ inlined script), and then -- to prove the JS actually runs and the event
handlers actually fire -- loads that file with `myjs.Page` and drives it
headlessly: type a todo, add it, toggle one done, switch the filter, and read
the DOM back at each step.

Open ``pyjs_app.html`` in a browser afterwards; it's the same code.
"""

from pathlib import Path

import myjs
from domonic_libs.pyjs import transpile

# ---------------------------------------------------------------------------
# the app -- plain Python. `document` / `addEventListener` are the browser's.
# ---------------------------------------------------------------------------
APP_PY = r'''
state = {"items": [], "filter": "all", "seq": 1}


def visible():
    f = state["filter"]
    return [it for it in state["items"]
            if f == "all" or (f == "active" and not it["done"]) or (f == "done" and it["done"])]


def render():
    rows = []
    for it in visible():
        cls = "row done" if it["done"] else "row"
        box = "checked" if it["done"] else ""
        rows.append(
            f'<li class="{cls}" data-id="{it["id"]}">'
            f'<input type="checkbox" data-act="toggle" data-id="{it["id"]}" {box}>'
            f'<span class="text">{it["text"]}</span>'
            f'<button class="del" data-act="del" data-id="{it["id"]}">delete</button>'
            f'</li>'
        )
    document.getElementById("list").innerHTML = "".join(rows)

    left = len([it for it in state["items"] if not it["done"]])
    document.getElementById("count").textContent = f"{left} left of {len(state['items'])}"

    for b in document.querySelectorAll("#filters button"):
        active = b.getAttribute("data-filter") == state["filter"]
        b.className = "on" if active else ""


def add(text):
    text = text.strip()
    if not text:
        return
    state["items"].append({"id": state["seq"], "text": text, "done": False})
    state["seq"] += 1
    render()


def toggle(item_id):
    for it in state["items"]:
        if it["id"] == item_id:
            it["done"] = not it["done"]
    render()


def remove(item_id):
    state["items"] = [it for it in state["items"] if it["id"] != item_id]
    render()


def on_add(event):
    box = document.getElementById("new")
    add(box.value)
    box.value = ""


def on_list_click(event):
    t = event.target
    act = t.getAttribute("data-act")
    if not act:
        return
    n = int(t.getAttribute("data-id"))
    if act == "toggle":
        toggle(n)
    elif act == "del":
        remove(n)


def on_filter(event):
    f = event.target.getAttribute("data-filter")
    if f:
        state["filter"] = f
        render()


document.getElementById("add").addEventListener("click", on_add)
document.getElementById("list").addEventListener("click", on_list_click)
document.getElementById("filters").addEventListener("click", on_filter)
render()
'''

APP_JS = transpile(APP_PY, minify=True)

HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>todo (written in Python)</title>
<style>
  body {{ font: 15px/1.5 system-ui, sans-serif; max-width: 30rem; margin: 3rem auto; color: #1a1a1a; }}
  h1 {{ font-size: 1.3rem; }}
  .bar {{ display: flex; gap: .5rem; }}
  input#new {{ flex: 1; padding: .5rem .6rem; border: 1px solid #cbd0d6; border-radius: 6px; }}
  button {{ padding: .5rem .8rem; border: 1px solid #cbd0d6; border-radius: 6px; background: #fff; cursor: pointer; }}
  button#add {{ background: #1a1a1a; color: #fff; border-color: #1a1a1a; }}
  ul {{ list-style: none; padding: 0; }}
  .row {{ display: flex; align-items: center; gap: .5rem; padding: .45rem 0; border-bottom: 1px solid #eee; }}
  .row.done .text {{ text-decoration: line-through; color: #9aa0a6; }}
  .text {{ flex: 1; }}
  .del {{ font-size: .8rem; color: #b3261e; border-color: #f1c6c2; }}
  #filters {{ display: flex; gap: .4rem; margin-top: .5rem; }}
  #filters button.on {{ background: #1a1a1a; color: #fff; border-color: #1a1a1a; }}
  #count {{ color: #6b7280; font-size: .85rem; margin-top: .6rem; }}
</style>
</head>
<body>
  <h1>todo <small style="font-weight:400;color:#9aa0a6">— logic transpiled from Python</small></h1>
  <div class="bar">
    <input id="new" placeholder="what needs doing?">
    <button id="add">add</button>
  </div>
  <ul id="list"></ul>
  <div id="filters">
    <button data-filter="all">all</button>
    <button data-filter="active">active</button>
    <button data-filter="done">done</button>
  </div>
  <p id="count"></p>
  <script>{APP_JS}</script>
</body>
</html>
"""

out = Path(__file__).with_name("pyjs_app.html")
out.write_text(HTML, encoding="utf-8")
print(f"wrote {out}  ({len(HTML)} bytes, {len(APP_JS)} of it transpiled JS)")
print(f"open it in a browser, or watch it run headless below:\n")

# ---------------------------------------------------------------------------
# drive the page headlessly -- proof the JS runs and the handlers fire
# ---------------------------------------------------------------------------
page = myjs.Page.load(str(out))
assert not page.errors, page.errors


def snap(label):
    rows = [li.textContent.replace("delete", "").strip() for li in page.query_all("#list li")]
    done = [li for li in page.query_all("#list li") if "done" in (li.getAttribute("class") or "")]
    print(f"  {label:<28} {page.text('#count'):<18} {rows}  ({len(done)} done)")


snap("initial (empty)")
for task in ("buy milk", "write the docs", "ship pyjs"):
    page.fill("#new", task)
    page.click("#add")
snap("added 3")

page.click('#list li:nth-child(2) input')     # toggle "write the docs"
snap("toggled #2")

page.click('#filters button[data-filter="active"]')
snap("filter: active")

page.click('#filters button[data-filter="done"]')
snap("filter: done")

page.click('#filters button[data-filter="all"]')
page.click('#list li:nth-child(1) .del')       # delete "buy milk"
snap("filter: all, deleted #1")

print(f"\nfinal DOM of #list:\n  {page.inner_html('#list')}")
