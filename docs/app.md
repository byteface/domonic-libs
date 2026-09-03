# domonic-libs API

`domonic-libs` collects DOM-shaped Python ports and an optional pywebview app wrapper. The core install should stay useful without pywebview installed: use domonic for DOM/SVG/events, keep JS ports faithful where they expose DOM wrinkles, and load pywebview only when examples need desktop windows, dialogs, menus, drag/drop, or transparency.

This file covers the **app wrapper** API. The ports each have their own section in the [README](../README.md); the **`dlx` command line** is documented in [cli.md](cli.md).

## Version

```python
import domonic_libs

print(domonic_libs.__version__)
```

## App

```python
app = App(
    "Title",
    width=800,
    height=600,
    debug=False,
    data_dir=None,
    transparent=False,
    background_color="#FFFFFF",
    frameless=False,
    vibrancy=False,
    text_select=False,
)
```

`data_dir` defaults to:

```text
~/.domonic-libs/<app-name>/
```

`transparent`, `background_color`, `frameless`, `vibrancy`, and `text_select` are passed to `pywebview.create_window(...)`. For a genuinely transparent window, set a transparent window background and avoid opaque CSS backgrounds:

```python
app = App("Overlay", transparent=True, background_color="#000000")
```

## Routes

Only the root route is used by the current renderer:

```python
@app.route("/")
def index():
    return main("Hello")
```

After a Python event callback completes, the root route is rendered again and the client reconciles the new markup against the live DOM in place (so a focused field keeps its caret, a slider keeps its drag).

## Events

Prefer domonic listeners:

```python
node.addEventListener(Event.CLICK, callback)
```

Use `on(...)` to attach a listener and return the same node:

```python
from domonic_libs import on

button_node = on(button("Save"), Event.CLICK, save)
```

The convenience `_on...` style also works:

```python
button("Save", _onclick=callback)
```

Callbacks receive domonic event classes where possible:

- `Event`
- `MouseEvent`
- `KeyboardEvent`
- `InputEvent`
- `FocusEvent`
- `PointerEvent`
- `WheelEvent`
- `SubmitEvent`

Return `False` to skip the automatic re-render:

```python
def on_input(event):
    state["draft"] = event.value
    return False
```

## File Drops

```python
@app.on_file_drop
def dropped(event):
    file = event.files[0]
    print(file.name, file.size, getattr(file, "path", ""))
```

The callback receives a domonic `Event("drop")` with `event.files`. Each file is an object with browser metadata (`name`, `size`, `type`, `lastModified`) and, when pywebview exposes it, `path` / `pywebviewFullPath`.

Return `False` to skip the automatic re-render after the drop.

## Timers

```python
app.every(1, tick)
```

Intervals below `60` are treated as seconds. Larger values are treated as milliseconds. A timer callback can return `False` to skip re-rendering.

## Menus

```python
app.menu(
    "File",
    app.menu_item("Open...", open_document),
    app.submenu(
        "Recent",
        app.menu_item("Example", open_example),
    ),
    app.menu_separator(),
    app.menu_item("Save", save_document),
)
```

Menu callbacks can either accept a domonic `Event("menu")` or accept no arguments. By default, the app refreshes after a menu callback. Pass `refresh=False` when the callback already refreshes or should not replace the DOM.

```python
app.menu_item("Reload", app.refresh, refresh=False)
```

## Focused Editor Commands

These helpers forward common focused-editor actions to the embedded browser:

```python
app.cut()
app.copy()
app.paste()
app.select_all()
```

They apply to the active editable browser control, such as a focused `textarea`. They return `False` so menu callbacks do not refresh the DOM afterwards.

## Files And JSON

Native dialogs:

```python
app.open_file(file_types=("Text files (*.txt)",))
app.open_folder()
app.save_file(filename="document.txt")
```

JSON persistence:

```python
settings = app.load_json("settings.json", default={})
app.save_json("settings.json", settings)
path = app.data_path("settings.json")
```

Text helpers:

```python
text = app.load_text("notes/today.txt", default="")
app.save_text("notes/today.txt", text)
files = app.data_files("notes/*.txt")
```

## Errors

If a browser event callback or timer callback raises, the app renders a simple callback error view with the exception and traceback.
