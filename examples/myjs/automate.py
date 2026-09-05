"""Drive a page's JavaScript from Python -- no browser.

    python examples/myjs/automate.py

`myjs.Page` parses the HTML, runs its <script>s against a real DOM, and then
lets you click / fill / wait / read like Puppeteer -- except it's a pure-Python
tree walker, not Chrome.
"""

import myjs

APP = """<!doctype html>
<html><head><title>Todo</title></head><body>
  <form id="new"><input id="text" placeholder="what needs doing"><button>Add</button></form>
  <ul id="list"></ul>
  <p id="count">0 items</p>
  <button id="clear">Clear done</button>
  <script>
    const list = document.getElementById("list");
    const countEl = document.getElementById("count");

    function render() {
      const items = list.querySelectorAll("li");
      const done = list.querySelectorAll("li.done").length;
      countEl.textContent = `${items.length} items, ${done} done`;
    }

    document.getElementById("new").addEventListener("submit", (e) => {
      e.preventDefault();
      const input = document.getElementById("text");
      if (!input.value.trim()) return;
      const li = document.createElement("li");
      li.textContent = input.value.trim();
      li.addEventListener("click", () => { li.classList.toggle("done"); render(); });
      list.appendChild(li);
      input.value = "";
      render();
    });

    document.getElementById("clear").addEventListener("click", () => {
      list.querySelectorAll("li.done").forEach((li) => li.remove());
      render();
    });
  </script>
</body></html>"""


page = myjs.Page(APP, url="https://example.com/todo")
print("loaded:", page.title, "at", page.eval("location.href"))

for task in ["buy milk", "write docs", "ship myjs"]:
    page.fill("#text", task)
    page.submit("#new")

print("after adding 3:", page.text("#count"))
print("  items:", [li.textContent for li in page.query_all("#list li")])

# click the first two todos to toggle them done
for li in page.query_all("#list li")[:2]:
    page.click(li)
print("after marking 2 done:", page.text("#count"))

page.click("#clear")
print("after clearing done:", page.text("#count"),
      "->", [li.textContent for li in page.query_all("#list li")])

print("\nfinal DOM:")
print(page.query("#list"))
