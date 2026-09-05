"""Write Python, get JavaScript that runs -- `domonic_libs.pyjs`.

The mirror of `myjs` (JS in Python): a Python subset is walked as a CPython
AST, translated to ESTree, and emitted by the acorn code generator. Here we
transpile a small program, print the JS, and -- to prove it -- run that JS
back through the interpreter and check it prints the same thing CPython does.

    python examples/pyjs_demo.py
"""

import subprocess
import sys

from domonic_libs.acorn.interpret import run_js
from domonic_libs.pyjs import transpile

PROGRAM = '''
def is_prime(n):
    if n < 2:
        return False
    for d in range(2, int(n ** 0.5) + 1):
        if n % d == 0:
            return False
    return True

class Sieve:
    def __init__(self, limit):
        self.limit = limit
    def primes(self):
        return [n for n in range(2, self.limit) if is_prime(n)]

s = Sieve(40)
found = s.primes()
print(f"{len(found)} primes under {s.limit}: {found}")
print("sum:", sum(found), " biggest:", max(found))
'''

print("=" * 64)
print("PYTHON")
print("=" * 64)
print(PROGRAM.strip())

js = transpile(PROGRAM, runtime=False)
print("=" * 64)
print("JAVASCRIPT  (dlx pyjs --no-runtime)")
print("=" * 64)
print(js)

mini = transpile(PROGRAM, minify=True)
print("=" * 64)
print(f"MINIFIED (with the __py runtime): {len(mini)} bytes")
print("=" * 64)

# run both and compare
ref = subprocess.run([sys.executable, "-c", PROGRAM], capture_output=True, text=True).stdout
_, lines = run_js(mini)
got = "\n".join(lines) + "\n"

print("CPython says:")
print("  " + ref.replace("\n", "\n  ").rstrip())
print("the transpiled JS says:")
print("  " + got.replace("\n", "\n  ").rstrip())
print()
print("match:", ref == got)
