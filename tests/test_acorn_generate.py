"""The ESTree -> JavaScript code generator (`domonic_libs.acorn.generate`).

The third leg of the acorn port -- ``parse`` reads JS, ``interpret`` runs an
AST, ``generate`` writes an AST back out. Verified by round-tripping: for a
wide spread of constructs, and for the whole js262 + conformance corpus,
``parse(generate(parse(src)))`` yields an equivalent tree, in both the
readable default and the minified mode. A minified program also still runs.
"""

import glob
import os

import pytest

from domonic_libs.acorn import generate, minify, parse
from domonic_libs.acorn.interpret import run_js

_OPTS = {
    "ecmaVersion": 2022, "sourceType": "module", "locations": True,
    "allowReturnOutsideFunction": True, "allowAwaitOutsideFunction": True,
}


def _norm(d, minified=False):
    """Drop position noise, stringify RegExp values, and -- for the minified
    comparison only -- treat an identifier-shaped string property key as an
    Identifier key (unquoting `{"a": 1}` -> `{a: 1}` is a legit minifier
    transform that leaves the program's meaning untouched)."""
    if isinstance(d, dict):
        d = {k: _norm(v, minified) for k, v in d.items()
             if k not in ("start", "end", "range", "loc", "raw")}
        if (minified and d.get("type") in ("Property", "MethodDefinition", "PropertyDefinition")
                and not d.get("computed")):
            key = d.get("key")
            if (isinstance(key, dict) and key.get("type") == "Literal"
                    and isinstance(key.get("value"), str)):
                d["key"] = {"type": "Identifier", "name": key["value"]}
        return d
    if isinstance(d, list):
        return [_norm(x, minified) for x in d]
    if isinstance(d, (str, int, float, bool, type(None))):
        return d
    return str(d)   # RegExp / other opaque -> its text form


def _roundtrips(src, *, minified):
    t1 = parse(src, dict(_OPTS))
    out = generate(t1, minify=minified)
    t2 = parse(out, dict(_OPTS))
    return _norm(t1.to_dict(), minified) == _norm(t2.to_dict(), minified), out


_CASES = [
    "const f = (x, y = 1, ...r) => x + y;",
    "a ** b ** c;",
    "(a + b) * c;",
    "a = b = c;",
    "a + +b; a - -b; a++ + ++b;",
    "-(-x); +(+y); !(!z);",
    "new Foo().bar; new Foo.Bar(1, 2); new (make())();",
    "(255).toString(16); (1.5).toFixed(2);",
    "a ? b : c ? d : e;",
    "let {a, b: c, d = 1, ...rest} = obj;",
    "const [x, , y, ...z] = arr;",
    "for (const x of items) log(x);",
    "for (let i = 0, n = a.length; i < n; i++) sum += a[i];",
    "for (const k in obj) if (has(k)) keys.push(k);",
    "do work(); while (again());",
    "label: while (true) { if (x) break label; else continue label; }",
    "const t = `a ${x} b ${y + 1} c`;",
    "tag`hi ${name}`;",
    "x?.y?.[z]?.() ?? w;",
    "switch (n) { case 1: case 2: f(); break; default: g(); }",
    "class A extends B { #p = 1; static s = 2; static { init(); } "
    "  m() { return this.#p; } get g() { return 1; } set g(v) {} *gen() { yield 1; } }",
    "const o = { a: 1, b, [c]: 3, 'x-y': 4, m() {}, *g() {}, async a() {}, get x() { return 1; }, ...rest };",
    "try { risky(); } catch { fallback(); } finally { cleanup(); }",
    "(function () { return 1; })(); (async () => await x)();",
    "const a = 1, b = 2; export const v = 1; export { a, b as c }; export default function () {};",
    "export * as ns from 'mod'; export { x } from 'other';",
    "import def, { named as n, other } from 'pkg'; import * as all from 'z'; import 'side-effect';",
    "throw new Error('boom'); void 0, typeof x, delete obj.k;",
    "const re = /foo\\d+/gimsu; const s = \"he said \\\"hi\\\"\";",
    "async function* stream() { yield* source; for await (const c of chunks) emit(c); }",
]


@pytest.mark.parametrize("src", _CASES, ids=range(len(_CASES)))
def test_pretty_round_trips(src):
    ok, out = _roundtrips(src, minified=False)
    assert ok, f"pretty round-trip changed the AST:\n{out}"


@pytest.mark.parametrize("src", _CASES, ids=range(len(_CASES)))
def test_minified_round_trips(src):
    ok, out = _roundtrips(src, minified=True)
    assert ok, f"minified round-trip changed the AST:\n{out}"
    assert "\n" not in out.rstrip("\n")   # genuinely one line


_SUITE = sorted(
    glob.glob(os.path.join(os.path.dirname(__file__), "..", "src", "domonic_libs", "js262", "suite", "*.js"))
    + glob.glob(os.path.join(os.path.dirname(__file__), "..", "src", "domonic_libs", "conformance", "suite", "*.js"))
)


@pytest.mark.parametrize("path", _SUITE, ids=[os.path.basename(p) for p in _SUITE])
def test_suite_files_round_trip_both_modes(path):
    src = open(path, encoding="utf-8").read()
    for minified in (False, True):
        ok, out = _roundtrips(src, minified=minified)
        assert ok, f"{'minified' if minified else 'pretty'} round-trip changed {os.path.basename(path)}"


def test_minified_program_still_runs():
    src = (
        "function fib(n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }\n"
        "const odds = [1, 2, 3, 4, 5].map(x => x * x).filter(x => x % 2 === 1);\n"
        "class Point { constructor(x, y) { this.x = x; this.y = y; } "
        "  dist() { return Math.sqrt(this.x ** 2 + this.y ** 2); } }\n"
        "console.log(fib(10), odds.join(','), new Point(3, 4).dist());\n"
    )
    mini = generate(parse(src, {"ecmaVersion": 2022}), minify=True)
    _, lines = run_js(mini)
    assert lines == ["55 1,9,25 5"]


def test_minify_helper_from_string_and_file(tmp_path):
    assert minify("const   x  =  1 ;") == "const x=1;"
    p = tmp_path / "a.js"
    p.write_text("function  f ( ) {\n  return  42 ;\n}\n")
    assert minify(str(p)) == "function f(){return 42;}"


def test_generate_accepts_a_plain_dict():
    tree = parse("const a = 1 + 2;", {"ecmaVersion": 2022})
    assert generate(tree.to_dict()) == generate(tree)


def test_dlx_minify_and_fmt_cli(capsys):
    from domonic_libs.cli import main

    import io
    import sys

    sys.stdin = io.StringIO("const   f = ( a , b )=>{ return a+b } ;")
    assert main(["minify"]) == 0
    assert capsys.readouterr().out.strip() == "const f=(a,b)=>{return a+b;};"

    sys.stdin = io.StringIO("const f=(a,b)=>{return a+b};")
    assert main(["fmt", "--indent", "4"]) == 0
    out = capsys.readouterr().out
    assert "    return a + b;" in out
