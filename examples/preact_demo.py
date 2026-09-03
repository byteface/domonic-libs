"""Preact playground: a todo app whose entire UI is built by the Preact port.

The list on the left is not domonic markup -- it is a Preact component tree
(``h(...)`` calls, state kept in Python) rendered into one persistent
``domonic`` container. Every interaction re-runs ``preact.render()`` into that
*same* container, so Preact's reconciler diffs the server-side DOM in place
rather than rebuilding it.

The container node itself is handed to the ``App`` shell (not a serialised
string), so ``App`` walks it and wires the buttons/inputs Preact produced back
to Python: after each ``preact.render`` the demo pokes a ``_onclick`` /
``_onchange`` callback onto every node carrying a ``data-act`` / ``data-edit`` /
``data-new`` marker, and ``App`` turns those into real event handlers.

The "reconciler" pane makes the diffing visible: before each render the demo
fingerprints every node in the container by ``id()``, and afterwards reports how
many were reused versus freshly created. Toggling one todo reuses nearly
everything; switching the filter rebuilds just the list.

Text edits commit on blur / Enter (the ``change`` event) -- the App refreshes
the whole body on every event, so re-rendering mid-keystroke would drop focus.
"""

from domonic.dom import document
from domonic.html import div, h1, h2, main, p, pre, style

from domonic_libs import App
from domonic_libs import preact
from domonic_libs.preact import Component, Fragment, h

app = App("Preact Playground", width=1120, height=760, text_select=True)

# ---------------------------------------------------------------------------
# Application state (plain Python -- Preact just renders a view of it).
# ---------------------------------------------------------------------------
state = {
    "todos": [
        {"id": 1, "text": "Port create-element", "done": True},
        {"id": 2, "text": "Port the reconciler", "done": True},
        {"id": 3, "text": "Port hooks", "done": False},
        {"id": 4, "text": "Write a demo", "done": False},
    ],
    "filter": "all",
    "next_id": 5,
}
report = {"reused": 0, "created": 0, "log": "Initial mount."}

# The container Preact owns for the life of the process.
container = document.createElement("div")


# ---------------------------------------------------------------------------
# Preact components
# ---------------------------------------------------------------------------
def TodoItem(props):
    todo = props["todo"]
    tid = str(todo["id"])
    return h(
        "li",
        {"class": "todo done" if todo["done"] else "todo"},
        h(
            "button",
            {"class": "check", "data-act": f"toggle:{tid}", "title": "toggle"},
            "✓" if todo["done"] else "",
        ),
        h(
            "input",
            {"class": "text", "data-edit": tid, "value": todo["text"]},
        ),
        h(
            "button",
            {"class": "del", "data-act": f"del:{tid}", "title": "delete"},
            "×",
        ),
    )


def visible_todos():
    f = state["filter"]
    if f == "active":
        return [t for t in state["todos"] if not t["done"]]
    if f == "done":
        return [t for t in state["todos"] if t["done"]]
    return list(state["todos"])


class TodoList(Component):
    """A class component, just to exercise that path in the port."""

    def render(self, props, st, ctx):
        todos = props["todos"]
        if not todos:
            return h("p", {"class": "empty"}, "Nothing here.")
        return h(
            "ul",
            {"class": "list"},
            *[h(TodoItem, {"todo": t, "key": t["id"]}) for t in todos],
        )


def FilterTabs(props):
    current = props["filter"]
    return h(
        "div",
        {"class": "tabs"},
        *[
            h(
                "button",
                {
                    "class": "tab active" if name == current else "tab",
                    "data-act": f"filter:{name}",
                },
                name,
            )
            for name in ("all", "active", "done")
        ],
    )


def AppView(props):
    remaining = sum(1 for t in state["todos"] if not t["done"])
    return h(
        Fragment,
        None,
        h(
            "header",
            None,
            h("strong", None, "todos"),
            h("span", {"class": "count"}, f"{remaining} left"),
        ),
        h("input", {"class": "new", "data-new": "1", "value": "", "placeholder": "Add a todo, then press Enter"}),
        h(FilterTabs, {"filter": props["filter"]}),
        h(TodoList, {"todos": props["todos"]}),
    )


# ---------------------------------------------------------------------------
# Rendering + reconciler instrumentation
# ---------------------------------------------------------------------------
def _fingerprint(node, acc):
    for child in list(getattr(node, "childNodes", []) or []):
        acc.add(id(child))
        _fingerprint(child, acc)
    return acc


def render_view(note=None):
    before = _fingerprint(container, set())
    preact.render(
        h(AppView, {"todos": visible_todos(), "filter": state["filter"]}), container
    )
    after = _fingerprint(container, set())
    report["reused"] = len(before & after)
    report["created"] = len(after - before)
    if note:
        report["log"] = note


# ---------------------------------------------------------------------------
# State transitions (each ends with a re-render)
# ---------------------------------------------------------------------------
def apply_action(action):
    if action.startswith("toggle:"):
        tid = int(action.split(":", 1)[1])
        for t in state["todos"]:
            if t["id"] == tid:
                t["done"] = not t["done"]
        render_view(f"toggled #{tid}")
    elif action.startswith("del:"):
        tid = int(action.split(":", 1)[1])
        state["todos"] = [t for t in state["todos"] if t["id"] != tid]
        render_view(f"deleted #{tid}")
    elif action.startswith("filter:"):
        state["filter"] = action.split(":", 1)[1]
        render_view(f"filter -> {state['filter']}")


def add_todo(text):
    n = state["next_id"]
    state["todos"].append({"id": n, "text": text, "done": False})
    state["next_id"] += 1
    render_view(f"added #{n}")


def set_text(tid, text):
    for t in state["todos"]:
        if t["id"] == tid:
            t["text"] = text
    render_view(f"edited #{tid}")


# ---------------------------------------------------------------------------
# Event handlers (generic -- read the marker off the event target)
# ---------------------------------------------------------------------------
def on_click(event=None):
    dataset = getattr(getattr(event, "target", None), "dataset", None)
    action = getattr(dataset, "act", None) if dataset else None
    if action:
        apply_action(action)


def on_change(event=None):
    target = getattr(event, "target", None)
    dataset = getattr(target, "dataset", None)
    value = getattr(target, "value", "") or ""
    if not dataset:
        return
    if getattr(dataset, "new", None):
        if value.strip():
            add_todo(value.strip())
    elif getattr(dataset, "edit", None):
        set_text(int(dataset.edit), value)


def _wire(node):
    """Poke Python callbacks onto the Preact-produced nodes so App can bind them."""
    for child in list(getattr(node, "childNodes", []) or []):
        kwargs = getattr(child, "kwargs", None)
        if isinstance(kwargs, dict) and hasattr(child, "getAttribute"):
            if child.getAttribute("data-act"):
                kwargs["_onclick"] = on_click
            if child.getAttribute("data-edit") or child.getAttribute("data-new"):
                kwargs["_onchange"] = on_change
        _wire(child)


render_view("Initial mount.")


@app.route("/")
def index():
    _wire(container)

    stats = pre(
        f"reused nodes : {report['reused']}\n"
        f"created nodes : {report['created']}\n"
        f"last action  : {report['log']}"
    )

    return main(
        style(CSS),
        div(
            div(
                h1("Preact Playground"),
                p(
                    "Every widget below is a Preact component tree rendered onto "
                    "domonic's server-side DOM and diffed in place on each change."
                ),
                _class="title",
            ),
            div(container, _class="app"),
            _class="left",
        ),
        div(
            div(h2("Reconciler"), stats, _class="pane"),
            div(h2("Serialised container"), pre(str(container)), _class="pane"),
            _class="right",
        ),
    )


CSS = """
body { margin: 0; background: #eef1f4; color: #1f2328; font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
main { display: grid; grid-template-columns: 380px 1fr; gap: 16px; height: 100vh; box-sizing: border-box; padding: 16px; }
h1 { font-size: 20px; margin: 0; }
h2 { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #5f6b76; margin: 0 0 6px; }
p { color: #53606b; }
.left { display: flex; flex-direction: column; gap: 14px; min-height: 0; }
.app { background: #fff; border: 1px solid #d3dae2; border-radius: 10px; padding: 16px; overflow: auto; }
.right { display: grid; grid-template-rows: auto 1fr; gap: 12px; min-height: 0; }
.pane { background: #fff; border: 1px solid #d3dae2; border-radius: 8px; padding: 12px; overflow: auto; min-height: 0; }
pre { margin: 0; font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; color: #1f2328; }
header { display: flex; justify-content: space-between; align-items: baseline; font-size: 22px; color: #b3403a; }
header .count { font-size: 12px; color: #6b7680; }
input { font: 13px inherit; color: #1f2328; background: #fff; border: 1px solid #c3ccd6; border-radius: 6px; padding: 6px 8px; }
input.new { width: 100%; box-sizing: border-box; margin: 12px 0; }
button { font: 13px inherit; border: 1px solid #c3ccd6; border-radius: 6px; background: #fff; color: #1f2328; cursor: pointer; padding: 5px 9px; }
button:hover { background: #f2f5f8; }
.tabs { display: flex; gap: 6px; margin: 6px 0 14px; }
.tab.active { background: #1f6feb; color: #fff; border-color: #1f6feb; }
.list { list-style: none; margin: 0; padding: 0; }
.todo { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #eceff2; }
.todo .text { flex: 1; border-color: transparent; background: transparent; }
.todo .text:focus { border-color: #c3ccd6; background: #fff; }
.todo.done .text { text-decoration: line-through; color: #9aa4ae; }
.check { width: 24px; height: 24px; border-radius: 50%; padding: 0; }
.del { border: none; background: none; color: #b3403a; font-size: 16px; }
.empty { color: #9aa4ae; }
"""


if __name__ == "__main__":
    app.run()
