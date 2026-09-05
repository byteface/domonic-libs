"""A .py file importing a .js file and calling it directly -- no CLI, no
subprocess, no serialization. A JS function is a real, callable Python
object (JSFunction implements __call__), so this is just Python calling
Python, where the "Python" happens to have been written in JavaScript.

    python examples/myjs/from_python.py
"""

from pathlib import Path

import myjs

mod = myjs.import_js(Path(__file__).parent / "greet.js")

print(mod.greet("World"))
print(f"fib(10) = {mod.fibonacci(10)}")
print(f"greet.js version: {mod.VERSION}")

# it's a real object either way -- attribute access and dict access both work
print(f"same function both ways: {mod.greet is mod['greet']}")
