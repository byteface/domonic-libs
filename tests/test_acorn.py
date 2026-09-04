"""Coverage for the acorn port -- leaf modules, tokenizer, and the regex-literal
validator.

acorn is ported primarily to stress ``domonic.javascript``. Every wrinkle it
surfaced is fixed in domonic 1.6 and is asserted here as a plain test (see
``docs/javascript-wrinkles.md``).
"""

import pytest

from domonic.javascript import RegExp, String
from domonic_libs import acorn
from domonic_libs.acorn import identifier, tokenize, util, whitespace


def labels(src, **opts):
    opts.setdefault("ecmaVersion", 2022)
    return [t.type.label for t in tokenize(src, opts)]


def toks(src, **opts):
    opts.setdefault("ecmaVersion", 2022)
    return [(t.type.label, t.value) for t in tokenize(src, opts)]


# -- what already works -------------------------------------------------------

def test_modules_import_and_build_the_big_regexes():
    # constructing nonASCIIidentifierStart / nonASCIIidentifier happens at import
    assert identifier.nonASCIIidentifierStart.source.startswith("[")
    assert acorn.version == "8.18.0"


def test_wordsRegexp_builds_and_matches():
    kw = util.wordsRegexp(identifier.keywords[5])
    assert bool(kw.test("function"))
    assert bool(kw.test("return"))
    assert not bool(kw.test("async"))
    assert not bool(kw.test("fun"))


def test_ascii_identifier_predicates():
    assert identifier.isIdentifierStart(ord("$"))
    assert identifier.isIdentifierStart(ord("_"))
    assert identifier.isIdentifierStart(ord("A"))
    assert not identifier.isIdentifierStart(ord("0"))
    assert identifier.isIdentifierChar(ord("0"))
    assert not identifier.isIdentifierChar(ord("-"))


def test_line_break_source_round_trips():
    assert whitespace.lineBreak.source == whitespace.lineBreakG.source
    assert bool(whitespace.lineBreak.test("\r\n"))
    assert not bool(whitespace.lineBreak.test("x"))


# -- tokenizer (second pass) -----------------------------------------------

def test_tokenize_basic_expression():
    assert toks("x = 1 + 2") == [
        ("name", "x"), ("=", "="), ("num", 1.0), ("+/-", "+"), ("num", 2.0), ("eof", None),
    ]


@pytest.mark.parametrize("src, value", [
    ("0x1F", 31.0), ("0b1010", 10.0), ("0o17", 15.0),
    ("1_000_000", 1000000.0), ("0.5e-3", 0.0005), (".25", 0.25),
    ("010", 8.0), ("089", 89.0),
])
def test_number_literals(src, value):
    assert toks(src) == [("num", value), ("eof", None)]


@pytest.mark.parametrize("src, out", [
    (r'"a\tb"', "a\tb"),
    (r'"\x41\x42"', "AB"),
    (r'"A"', "A"),
    (r'"\u{1F600}"', "\U0001F600"),
    (r"'\101'", "A"),
])
def test_string_escapes(src, out):
    assert toks(src) == [("string", out), ("eof", None)]


def test_template_with_substitution():
    assert labels("`a${b}c`") == ["`", "template", "${", "name", "}", "template", "`", "eof"]


def test_regex_vs_divide_disambiguation():
    assert labels("a / b / c") == ["name", "/", "name", "/", "name", "eof"]
    assert labels("return /x/g.test(s)")[:2] == ["return", "regexp"]
    assert labels("/[/]/g") == ["regexp", "eof"]  # '/' inside a class does not end it


def test_non_ascii_identifiers():
    # exercises the wrinkle-#1 workaround in identifier.py
    assert toks("café + λ") == [("name", "café"), ("+/-", "+"), ("name", "λ"), ("eof", None)]


def test_unicode_escape_identifier():
    assert toks(r"a = 1") == [("name", "a"), ("=", "="), ("num", 1.0), ("eof", None)]


def test_modern_operators():
    assert labels("x = a?.b ?? c") == ["name", "=", "name", "?.", "name", "??", "name", "eof"]
    assert labels("a >>>= b") == ["name", "_=", "name", "eof"]
    assert labels("this.#x") == ["this", ".", "privateId", "eof"]


@pytest.mark.parametrize("src", ["3in x", "0x", "'unterminated", "1 + @"])
def test_tokenizer_raises_on_invalid(src):
    with pytest.raises(SyntaxError):
        toks(src)


# -- domonic.javascript behaviour the port relies on (see docs/javascript-wrinkles.md) --
# The first four were first-pass wrinkles, fixed in domonic 1.6.

def test_string_fromcharcode_is_static():
    assert String.fromCharCode(65) == "A"
    assert String.fromCharCode(65, 66) == "AB"
    assert str(String.fromCharCode(0xD83D, 0xDE00)) == "\U0001F600"  # surrogate pair recombines


def test_charcodeat_past_end_is_numeric_nan():
    r = String("ab").charCodeAt(5)
    assert not (r <= 0xFFFF)  # NaN comparison is False, not a TypeError


def test_caret_empty_class_matches_any_char():
    assert bool(RegExp("a[^]b").test("a\nb"))


def test_string_is_utf16_indexed():
    s = String("a\U0001F600b")
    assert s.length == 4
    assert s.charCodeAt(1) == 0xD83D


def test_tokenizer_handles_astral_source():
    # astral identifier (U+1D6FC is ID_Start) and \u{...} escape, with offsets
    assert toks("\U0001D6FC = 1") == [
        ("name", "\U0001D6FC"), ("=", "="), ("num", 1.0), ("eof", None),
    ]
    assert toks(r'"\u{1F600}"') == [("string", "\U0001F600"), ("eof", None)]
    strtok = next(iter(tokenize('"\U0001F600"+1', {"ecmaVersion": 2022})))
    assert (strtok.start, strtok.end) == (0, 4)  # emoji is two UTF-16 units


def test_escaped_backslash_then_empty_class():
    assert bool(RegExp(r"\\[^]").test("\\x"))


def test_string_raw_is_static():
    assert String.raw({"raw": ["a", "b"]}, 1) == "a1b"


# -- regex-literal validator (regexp.js) -----------------------------------

@pytest.mark.parametrize("src, ev", [
    (r"/(a)(b)\2\1/", 2022),
    (r"/(?<year>\d{4})-\d{2}/", 2022),
    (r"/\p{Script=Greek}/u", 2022),
    (r"/\u{1D11E}/u", 2022),
    (r"/\k<a>(?<a>b)/u", 2022),
    (r"/[\p{Alpha}&&\p{ASCII}]/v", 2024),
    (r"/[\q{ab|cd}]/v", 2024),
    (r"/(?<a>x)|(?<a>y)/", 2025),  # same name, separate branches -- ES2025
])
def test_valid_regex_literals(src, ev):
    tok = tokenize(src, {"ecmaVersion": ev})[0]
    assert tok.type.label == "regexp"


@pytest.mark.parametrize("src", [
    r"/a{3,2}/",            # quantifier out of order
    r"/(?<n>a)(?<n>b)/",    # duplicate group name (same branch)
    r"/\p{Bogus=Nope}/u",   # invalid property
    r"/[b-a]/",             # class range out of order
    r"/(unclosed/",         # unterminated group
    r"/\99/u",              # backreference past capture count
    r"/\u{110000}/u",       # code point out of range
    r"/(?<1bad>x)/u",       # invalid group name
])
def test_invalid_regex_literals_raise(src):
    with pytest.raises(SyntaxError):
        tokenize(src, {"ecmaVersion": 2022})


def test_strict_directive_detected():
    from domonic_libs.acorn import Tokenizer
    assert Tokenizer.tokenizer('"use strict"; x', {"ecmaVersion": 2022}).strict
    assert not Tokenizer.tokenizer("x = 1", {"ecmaVersion": 2022}).strict
    # legacy octal is a SyntaxError under a detected "use strict"
    with pytest.raises(SyntaxError):
        tokenize('"use strict"; 010', {"ecmaVersion": 2022})


def test_string_index_past_end_is_undefined():
    assert String("abc")[3] is None


# -- parser (statement.js / expression.js / lval.js) ----------------------

def _ast(src, **opts):
    from domonic_libs.acorn import parse
    opts.setdefault("ecmaVersion", 2022)
    return parse(src, opts).to_dict()


def test_parse_program_shape():
    t = _ast("const f = x => x * 2")
    assert t["type"] == "Program" and t["sourceType"] == "script"
    decl = t["body"][0]
    assert decl["type"] == "VariableDeclaration" and decl["kind"] == "const"
    arr = decl["declarations"][0]["init"]
    assert arr["type"] == "ArrowFunctionExpression"
    assert arr["body"]["type"] == "BinaryExpression" and arr["body"]["operator"] == "*"


def test_parse_operator_precedence():
    e = _ast("1 + 2 * 3 ** 2 - 4")["body"][0]["expression"]
    assert e["operator"] == "-"
    assert e["left"]["operator"] == "+"
    assert e["left"]["right"]["right"]["operator"] == "**"  # right-associative


def test_parse_optional_chaining():
    es = _ast("a.b().c?.d")["body"][0]["expression"]
    assert es["type"] == "ChainExpression"


def test_parse_destructuring():
    idn = _ast("const {x, y: z = 1, ...r} = o")["body"][0]["declarations"][0]["id"]
    assert idn["type"] == "ObjectPattern"
    assert idn["properties"][0]["shorthand"] is True
    assert idn["properties"][1]["value"]["type"] == "AssignmentPattern"
    assert idn["properties"][2]["type"] == "RestElement"


def test_parse_class():
    body = _ast("class A extends B { static #p = 1; static { 0 } m(){ super.m() } }")["body"][0]["body"]["body"]
    assert body[0]["type"] == "PropertyDefinition" and body[0]["key"]["type"] == "PrivateIdentifier"
    assert body[1]["type"] == "StaticBlock"
    assert body[2]["type"] == "MethodDefinition"


def test_parse_module():
    t = _ast("import x, {y as z} from 'm'; export default function(){}", sourceType="module")
    assert t["body"][0]["type"] == "ImportDeclaration"
    assert t["body"][0]["specifiers"][1]["local"]["name"] == "z"
    assert t["body"][1]["type"] == "ExportDefaultDeclaration"


@pytest.mark.parametrize("bad", [
    "let 1x = 2", "function (){}", "for (;;", "class {", "return 5",
    "const x", "a ** b **", "{", "case 1:", "break outer",
])
def test_parse_errors_raise(bad):
    from domonic_libs.acorn import parse
    with pytest.raises(SyntaxError):
        parse(bad, {"ecmaVersion": 2022})


def test_parse_realworld_snippet():
    src = (
        "const cache = new Map();\n"
        "export function memoize(fn) {\n"
        "  return (...args) => {\n"
        "    const key = JSON.stringify(args);\n"
        "    return cache.has(key) ? cache.get(key) : cache.set(key, fn(...args)).get(key);\n"
        "  };\n"
        "}\n"
        "async function* gen() { yield* [1,2,3]; }\n"
        "label: for (let i = 0; i < 10; i++) if (i % 2) continue label;\n"
    )
    kinds = [s["type"] for s in _ast(src, sourceType="module")["body"]]
    assert kinds == ["VariableDeclaration", "ExportNamedDeclaration", "FunctionDeclaration", "LabeledStatement"]


def test_parse_parenthesized_arrow_params():
    # exercises parseParenItem as `afterLeftParse`
    e = _ast("const f = (a, b = 1, {c}) => a + b + c")["body"][0]["declarations"][0]["init"]
    assert e["type"] == "ArrowFunctionExpression"
    assert [p["type"] for p in e["params"]] == ["Identifier", "AssignmentPattern", "ObjectPattern"]
    seq = _ast("(1, 2, 3)")["body"][0]["expression"]
    assert seq["type"] == "SequenceExpression" and len(seq["expressions"]) == 3


def test_parse_expression_at():
    from domonic_libs.acorn import parse_expression_at
    node = parse_expression_at("xx = 1 + 2 yy", 5, {"ecmaVersion": 2022})
    assert node.type == "BinaryExpression" and node.operator == "+"
