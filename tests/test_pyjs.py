"""``domonic_libs.pyjs`` -- Python -> JavaScript.

The proof is end to end: transpile Python, run the JavaScript through the
interpreter, and check the output matches what CPython would print.
"""

import subprocess
import sys

import pytest

from domonic_libs.acorn.interpret import run_js
from domonic_libs.pyjs import PyJSError, transpile


def _run_py(src):
    """What CPython prints for `src` -- the reference output."""
    r = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True, timeout=15)
    assert r.returncode == 0, r.stderr
    return r.stdout.splitlines()


def _run_js(src):
    _, lines = run_js(transpile(src, minify=True))
    return lines


CASES = [
    'print("hello world")',
    "def add(a, b):\n    return a + b\nprint(add(2, 3), add(-1, 1))",
    "def fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)\nprint(fib(12))",
    "print([x * x for x in range(6) if x % 2 == 0])",
    "print({c: c.upper() for c in 'abc'})",
    "for i, c in enumerate('abc'):\n    print(i, c)",
    "d = {'a': 1, 'b': 2}\n"
    "print(sorted(d.keys()), sum(d.values()), 'a' in d, len(d))",
    "class Point:\n"
    "    def __init__(self, x, y):\n        self.x, self.y = x, y\n"
    "    def norm2(self):\n        return self.x ** 2 + self.y ** 2\n"
    "print(Point(3, 4).norm2())",
    "class Base:\n    def tag(self):\n        return 'B'\n"
    "class Sub(Base):\n    def tag(self):\n        return 'S'\n"
    "print(Base().tag(), Sub().tag())",
    "name = 'ada'\nprint(f'hi {name.upper()}! {2 + 3 * 4}')",
    "print('a,b,c'.split(','), '-'.join(['x', 'y', 'z']))",
    "print('Hello World'.lower().replace('o', '0'))",
    "xs = [5, 2, 8, 1]\nxs.append(3)\nprint(sorted(xs), max(xs), min(xs))",
    "total = 0\nn = 1\nwhile n <= 100:\n    total += n\n    n += 1\nprint(total)",
    "def gen():\n    for i in range(3):\n        yield i * 10\nprint(list(gen()))",
    "try:\n    raise ValueError('nope')\nexcept Exception as e:\n    print('caught')\nfinally:\n    print('done')",
    "print(list(map(lambda x: x + 1, range(4))), list(filter(lambda x: x > 2, range(6))))",
    "a, b = 1, 2\na, b = b, a\nprint(a, b)",
    "print(not [], not [0], not '', not 'x')",   # `not` uses Python truthiness
    "print(bool([]), bool([0]), bool(''), bool('x'), bool(0), bool(None))",
    "import math\n"
    "print(math.floor(3.7), math.ceil(3.2), round(math.sqrt(2), 4), math.pi > 3.14)",
    "from math import cos, pi\nprint(int(round(cos(pi))))",
    "import math\nprint(int(round(math.log(8, 2))), int(math.hypot(3, 4)))",
    # -- Tier 1: floored modulo, f-string format specs, element-wise compare
    "print(-7 % 3, 7 % -3, -7 // 2, 5 % 2)",
    "x = 3.14159\nprint(f'{x:.2f}  [{x:>10.3f}]  {1234567:,}  {255:#06x}  {0.5:.0%}')",
    "print(f'[{5:04d}]', f'[{-3:+}]', f'[{\"hi\":^6}]', f'{[1, 2]!r}')",
    "print((1, 2) < (1, 3), [1, 2, 3] == [1, 2, 3], {'a': 1} == {'a': 1}, [1] in [[1], [2]])",
    # -- Tier 2: builtins
    "q, r = divmod(17, 5)\nprint(chr(65), ord('A'), hex(255), oct(8), bin(5), q, r)",
    "print(list(reversed(range(4))), list(map(str, [1, 2, 3])))",
    "print(min(['aa', 'b', 'ccc'], key=len), max([1, 5, 2], default=0), max([], default=-1))",
    "print(isinstance({}, dict), isinstance([], list), isinstance('x', str), isinstance(3, int))",
    # -- Tier 2: list / dict / set / str methods
    "a = [1]\na.extend([2, 3])\na.insert(0, 0)\na.remove(2)\nprint(a, a.index(3), a.count(1))",
    "a = [3, 1, 2]\na.sort(reverse=True)\nprint(a.pop(), a.pop(0), a)",
    "d = {'a': 1}\nd.setdefault('b', []).append(9)\nd.update({'c': 3})\n"
    "print([list(kv) for kv in sorted(d.items())], d.pop('a'), d.get('z', 'def'))",
    "s = {1, 2, 3}\ns.add(4)\ns.discard(9)\nprint(sorted(s & {2, 3, 9}), sorted(s | {5}), sorted(s - {1}))",
    "print('..hi..'.strip('.'), 'a  b   c'.split(), 'a-b-c'.replace('-', '+'))",
    "print('hello world'.title(), 'ABC'.swapcase(), '42'.zfill(5), 'x'.center(5, '-'))",
    "print('123'.isdigit(), 'abc'.isalpha(), 'Hello'.startswith('He'), 'ab\\ncd'.splitlines())",
]


@pytest.mark.parametrize("src", CASES, ids=range(len(CASES)))
def test_transpiled_output_matches_cpython(src):
    assert _run_js(src) == _run_py(src)


def test_no_runtime_output_is_clean():
    js = transpile("def sq(x): return x * x\nfor n in range(3): pass", runtime=False)
    assert "__py" in js  # range still needs it
    assert js.startswith("function sq(x)")


def test_minified_is_one_line_and_smaller_ratio():
    src = "\n".join(f"def f{i}(a, b):\n    return a + b + {i}" for i in range(20))
    pretty = transpile(src, minify=False, runtime=False)
    mini = transpile(src, minify=False, runtime=False)  # sanity
    small = transpile(src, minify=True, runtime=False)
    assert "\n" not in small.rstrip("\n")
    assert len(small) < len(pretty)


def test_unsupported_construct_raises_pyjserror():
    with pytest.raises(PyJSError):
        transpile("import os")
    with pytest.raises(PyJSError):
        transpile("with open('x') as f:\n    pass")


def test_number_display_gap_vs_cpython():
    # JS has one number type: an integral float prints without the trailing
    # `.0` that CPython shows (`4 ** 0.5` is `'2.0'` there, `'2'` here). The
    # value is right; only `str()` of it differs.
    assert _run_js("print(4 ** 0.5)") == ["2"]
    assert _run_js("print(6 / 2)") == ["3"]


def test_random_maps_to_math_random():
    # `random.*` isn't deterministic -- check the shapes/ranges instead.
    src = (
        "import random\n"
        "xs = [random.randint(0, 9) for _ in range(200)]\n"
        "print(all(0 <= x <= 9 for x in xs), len(xs))\n"
        "seq = [1, 2, 3, 4, 5]\n"
        "random.shuffle(seq)\n"
        "print(sorted(seq))\n"
        "print(random.choice(['only']))\n"
        "print(0.0 <= random.random() < 1.0)"
    )
    assert _run_js(src) == ["True 200", "[1, 2, 3, 4, 5]", "only", "True"]


def test_int_keyed_dict_becomes_a_map():
    # a plain JS object can't model integer keys (they'd stringify and, in a
    # real browser, reorder), so a non-string-keyed dict literal compiles to a
    # real `Map`. (myjs's Map still stringifies keys -- a browser's does not --
    # but insertion order and item access are right either way.)
    js = transpile("d = {2: 'a', 1: 'b'}\nprint(list(d))", runtime=False)
    assert "new Map(" in js
    assert _run_js("d = {3: 'c', 1: 'a', 2: 'b'}\nd[10] = 'x'\n"
                   "print(d[1], len(d), 1 in d, 9 in d, [str(k) for k in d])") == \
        ["a 4 True False ['3', '1', '2', '10']"]


def test_set_operators_need_a_syntactic_set():
    # `{1, 2} & other` works; `a & b` for two plain names stays bitwise-and,
    # so set algebra on variables must go through the methods.
    assert _run_js("print(sorted({1, 2, 3} & {2, 3}))") == ["[2, 3]"]
    assert _run_js("a = 6\nb = 3\nprint(a & b)") == ["2"]           # still int
    assert _run_js("a = {1, 2, 3}\nb = {2, 3}\n"
                   "print(sorted(a.intersection(b)))") == ["[2, 3]"]


def test_augmented_modulo_is_floored():
    assert _run_js("x = -7\nx %= 3\nprint(x)") == ["2"]
    assert _run_js("d = {'n': -7}\nd['n'] %= 3\nprint(d['n'])") == ["2"]


def test_import_of_unknown_module_still_raises():
    with pytest.raises(PyJSError):
        transpile("import numpy as np")
    with pytest.raises(PyJSError):
        transpile("from collections import Counter")


def test_dlx_pyjs_cli(capsys):
    import io

    from domonic_libs.cli import main

    sys.stdin = io.StringIO("def greet(n):\n    return f'hi {n}'\nprint(greet('x'))")
    assert main(["pyjs", "--minify"]) == 0
    out = capsys.readouterr().out
    _, lines = run_js(out)
    assert lines == ["hi x"]
