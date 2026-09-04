"""The tree-walking JS evaluator (`interpret.py`)."""

import pytest

from domonic_libs.acorn.interpret import run_js


def out(src):
    _doc, lines = run_js(src)
    return lines


@pytest.mark.parametrize("src, expected", [
    ("console.log(1 + 2 * 3)", ["7"]),
    ("console.log(`n=${2 ** 5}`)", ["n=32"]),
    ("console.log(typeof 1, typeof 'x', typeof undefined, typeof [])", ["number string undefined object"]),
    ("console.log('a' + 1, 1 + '1', 2 + 2)", ["a1 11 4"]),
    ("console.log(1 == '1', 1 === '1', null == undefined, NaN === NaN)", ["true false true false"]),
    ("let x = 5; x += 3; x **= 2; console.log(x)", ["64"]),
    ("console.log([3,1,2].sort().join(''), [1,2,3].reduce((a,b)=>a+b))", ["123 6"]),
    ("console.log('Hello World'.split(' ').map(w=>w[0]).join(''))", ["HW"]),
])
def test_expressions(src, expected):
    assert out(src) == expected


def test_functions_and_closures():
    assert out(
        "function adder(n){ return x => x + n; }\n"
        "const add10 = adder(10);\n"
        "console.log(add10(5), add10(-2));"
    ) == ["15 8"]


def test_recursion():
    assert out("function f(n){ return n<2?n:f(n-1)+f(n-2) } console.log(f(12))") == ["144"]


def test_control_flow():
    assert out(
        "let s = 0;\n"
        "for (let i = 1; i <= 10; i++) { if (i % 2) continue; s += i; }\n"
        "console.log(s);"
    ) == ["30"]


def test_try_catch_throw():
    assert out(
        "try { JSON.parse('{'); throw new TypeError('nope'); }\n"
        "catch (e) { console.log(e.name || 'err'); }\n"
        "finally { console.log('done'); }"
    )[-1] == "done"


def test_destructuring():
    assert out(
        "const {a, b: [c, d = 9], ...rest} = {a: 1, b: [2], x: 3};\n"
        "console.log(a, c, d, JSON.stringify(rest));"
    ) == ['1 2 9 {"x":3}']


def test_classes():
    assert out(
        "class Shape { constructor(name){ this.name = name; } describe(){ return this.name; } }\n"
        "class Circle extends Shape {\n"
        "  radius = 1;\n"
        "  constructor(r){ super('circle'); this.radius = r; }\n"
        "  describe(){ return super.describe() + ' r=' + this.radius; }\n"
        "  get area(){ return 3.14 * this.radius ** 2; }\n"
        "}\n"
        "const c = new Circle(2);\n"
        "console.log(c.describe(), c instanceof Shape);"
    ) == ["circle r=2 true"]


def test_runs_against_live_dom():
    doc, lines = run_js(
        "const list = document.createElement('ul');\n"
        "for (const item of ['a', 'b', 'c']) {\n"
        "  const li = document.createElement('li');\n"
        "  li.textContent = item.toUpperCase();\n"
        "  list.appendChild(li);\n"
        "}\n"
        "document.body.appendChild(list);\n"
        "console.log('items:', list.childNodes.length);"
    )
    assert lines == ["items: 3"]
    assert str(doc.body) == "<body><ul><li>A</li><li>B</li><li>C</li></ul></body>"


def test_reaches_domonic_window_api():
    doc, lines = run_js(
        "window.console.log('via window', window === globalThis);\n"
        "console.log(window.atob('aGk='));\n"
        "console.log(typeof window.location, typeof window.navigator, typeof setTimeout);\n"
        "const el = window.document.createElement('span');\n"
        "el.textContent = 'ok';\n"
        "window.document.body.appendChild(el);\n"
    )
    assert lines[0] == "via window true"
    assert lines[1] == "hi"
    assert lines[2] == "object object function"
    assert str(doc.body) == "<body><span>ok</span></body>"


def test_cssom_and_classlist_passthrough():
    # el.style / el.classList are domonic's CSSStyleDeclaration / DOMTokenList,
    # reached through js_get's attribute fallback -- no binding needed.
    doc, log = run_js(
        "const box = document.createElement('div');\n"
        "box.style.color = 'crimson';\n"
        "box.style.setProperty('padding', '8px');\n"
        "box.classList.add('panel');\n"
        "box.classList.toggle('active');\n"
        "document.body.appendChild(box);\n"
        "console.log(box.style.cssText);\n"
        "console.log(box.classList.contains('panel'), box.className);\n"
    )
    assert log[0] == "color: crimson; padding: 8px;"
    assert log[1] == "true panel active"


def test_events():
    _doc, log = run_js(
        "const el = document.createElement('button');\n"
        "el.addEventListener('click', () => console.log('clicked'));\n"
        "el.dispatchEvent(new Event('click'));\n"
    )
    assert log == ["clicked"]


@pytest.mark.parametrize("src, expected", [
    ("const u = new URL('https://x.io/p?q=1&r=2'); console.log(u.pathname, u.searchParams.get('r'))", ["/p 2"]),
    ("const p = new URLSearchParams('a=1&b=2'); console.log(p.get('a'), p.has('b'))", ["1 true"]),
    ("console.log(new TextEncoder().encode('hi').length)", ["2"]),
    ("const h = new Headers(); h.set('X-A', '1'); console.log(h.get('X-A'))", ["1"]),
    ("const r = new DOMRect(0, 0, 100, 50); console.log(r.width, r.height)", ["100 50"]),
    ("const p = new DOMPoint(3, 4); console.log(p.x, p.y)", ["3 4"]),
])
def test_webapi_constructors(src, expected):
    assert out(src) == expected


# The whole domonic.javascript / webapi.* / dom constructor surface is
# auto-bound -- if a domonic module disappears these stop resolving.
@pytest.mark.parametrize("name", [
    "URL", "URLSearchParams", "URLPattern", "Headers", "Request", "Response",
    "Blob", "File", "FileReader", "FormData", "XMLHttpRequest", "EventSource",
    "TextEncoder", "TextDecoder", "Event", "CustomEvent", "MouseEvent",
    "MessageChannel", "BroadcastChannel", "MutationObserver", "ResizeObserver",
    "IntersectionObserver", "Range", "NodeIterator", "TreeWalker",
    "DOMRect", "DOMPoint", "DOMMatrix", "DOMException", "Notification",
    "XPathEvaluator", "Path2D", "ImageData", "FontFace", "Worker",
    "Performance", "Clipboard", "Crypto", "Storage", "Reflect", "Intl",
])
def test_constructor_is_bound(name):
    assert out(f"console.log(typeof {name})") == ["function"] or \
        out(f"console.log(typeof {name})") == ["object"]  # Reflect/Intl are objects


def test_document_forwards_to_backing():
    _doc, log = run_js(
        "document.title = 'X';\n"
        "const c = document.createComment('note');\n"
        "console.log(document.title, typeof document.evaluate);"
    )
    assert log == ["X function"]


@pytest.mark.parametrize("src, expected", [
    ("console.log(String(42), String(null), String())", ["42 null "]),
    ("console.log(typeof String(1), 'x'.length)", ["string 1"]),
    ("console.log(Number('7') + 1, Number.isInteger(3), Number.isInteger(3.5))", ["8 true false"]),
    ("console.log(Boolean(0), Boolean('x'), Boolean())", ["false true false"]),
    ("try { null.x } catch (e) { console.log(e instanceof TypeError, e instanceof Error, TypeError.name) }",
     ["true true TypeError"]),
])
def test_string_number_boolean_and_error_instanceof(src, expected):
    assert out(src) == expected


def test_dataset_reads_and_writes_through_the_dom():
    doc, log = run_js(
        "const d = document.createElement('div');\n"
        "d.dataset.userId = '7';\n"
        "console.log(d.getAttribute('data-user-id'), 'userId' in d.dataset);\n"
        "d.setAttribute('data-role', 'admin');\n"
        "console.log(d.dataset.role);\n"
        "delete d.dataset.userId;\n"
        "console.log(d.hasAttribute('data-user-id'));\n"
    )
    assert log == ["7 true", "admin", "false"]


@pytest.mark.parametrize("src, expected", [
    ("Promise.resolve(1).then(v => console.log('then', v))", ["then 1"]),
    ("Promise.reject(new Error('x')).catch(e => console.log('catch', e.message))", ["catch x"]),
    ("Promise.resolve(2).then(v => v * 10).then(v => console.log(v))", ["20"]),
    ("(async () => { const v = await Promise.resolve(41); console.log(v + 1); })()", ["42"]),
    ("(async () => { try { await Promise.reject(new TypeError('no')); } "
     "catch (e) { console.log(e.name); } })()", ["TypeError"]),
    ("(async () => { const r = await Promise.all([1, Promise.resolve(2), 3]); "
     "console.log(r.join(',')); })()", ["1,2,3"]),
])
def test_event_loop(src, expected):
    assert out(src) == expected


def test_microtasks_run_before_timers():
    assert out(
        "setTimeout(() => console.log('timeout'), 0);\n"
        "Promise.resolve().then(() => console.log('micro'));\n"
        "console.log('sync');\n"
    ) == ["sync", "micro", "timeout"]


def test_settimeout_fires_after_script():
    assert out("setTimeout(() => console.log('later'), 5); console.log('now');") == ["now", "later"]


def test_clear_timeout_cancels():
    assert out(
        "const id = setTimeout(() => console.log('should not run'), 10);\n"
        "clearTimeout(id);\n"
        "console.log('cleared');\n"
    ) == ["cleared"]


def test_await_on_a_non_promise_passes_through():
    assert out("(async () => console.log(await 7))()") == ["7"]


@pytest.mark.parametrize("src, expected", [
    ("function* g(){ yield 1; yield 2; yield 3; } console.log([...g()].join(','))", ["1,2,3"]),
    ("function* g(){ const x = yield 1; yield x + 1; } const it = g();"
     "console.log(it.next().value, it.next(10).value, it.next().done)", ["1 11 true"]),
    ("function* g(){ yield* [1,2]; yield 3; } console.log([...g()].join(','))", ["1,2,3"]),
])
def test_generators(src, expected):
    assert out(src) == expected


def test_getters_and_setters():
    assert out(
        "const o = { _v: 1, get v(){ return this._v; }, set v(x){ this._v = x * 2; } };\n"
        "console.log(o.v); o.v = 5; console.log(o.v);"
    ) == ["1", "10"]


def test_class_accessors():
    assert out(
        "class C { constructor(){ this._n = 0; } get n(){ return this._n; } set n(x){ this._n = x + 1; } }\n"
        "const c = new C(); c.n = 9; console.log(c.n);"
    ) == ["10"]


def test_call_apply_bind():
    assert out(
        "function f(a, b){ return a + b + this.base; }\n"
        "console.log(f.call({base: 100}, 1, 2), f.apply({base: 10}, [3, 4]), "
        "f.bind({base: 1}, 5)(6));"
    ) == ["103 17 12"]


def test_labelled_break_and_continue():
    assert out(
        "let hits = 0;\n"
        "outer: for (let i = 0; i < 3; i++) {\n"
        "  for (let j = 0; j < 3; j++) { if (i === 1 && j === 1) break outer; hits++; }\n"
        "}\n"
        "console.log(hits);"
    ) == ["4"]


def test_per_iteration_let_binding():
    assert out(
        "const fns = [];\n"
        "for (let i = 0; i < 3; i++) fns.push(() => i);\n"
        "console.log(fns.map(f => f()).join(','));"
    ) == ["0,1,2"]


def test_const_reassignment_throws_type_error():
    from domonic_libs.acorn.interpret import JSThrow

    with pytest.raises(JSThrow) as ei:
        run_js("const c = 1; c = 2;")
    assert ei.value.value["name"] == "TypeError"


def test_object_freeze_and_hasownproperty():
    assert out(
        "const o = Object.freeze({ a: 1 });\n"
        "try { o.a = 2; } catch (e) {}\n"
        "console.log(o.a, o.hasOwnProperty('a'), o.hasOwnProperty('z'), Object.isFrozen(o));"
    ) == ["1 true false true"]


def test_json_reviver_and_replacer():
    assert out(
        "console.log(JSON.parse('{\"a\":1,\"b\":2}', (k, v) => typeof v === 'number' ? v * 10 : v).a);\n"
        "console.log(JSON.stringify({ a: 1, b: 2 }, (k, v) => k === 'b' ? undefined : v));\n"
        "console.log(JSON.stringify(undefined));"
    ) == ["10", '{"a":1}', "undefined"]


def test_astral_strings_are_utf16_indexed():
    assert out(
        "const s = 'a\\u{1F600}b';\n"
        "console.log(s.length, s.charCodeAt(1), s.slice(0, 1));"
    ) == ["4 55357 a"]


def test_thrown_error_reports_line_and_stack():
    from domonic_libs.acorn.interpret import JSThrow

    src = (
        "function a(){ b(); }\n"
        "function b(){ throw new TypeError('boom'); }\n"
        "a();\n"
    )
    with pytest.raises(JSThrow) as ei:
        run_js(src)
    err = ei.value
    assert err.js_line == 2
    assert err.js_trace == "b → a → <script>"
    assert "at b → a → <script> (line 2)" in err.value["stack"]


def test_reference_error_in_constructor_has_trace():
    from domonic_libs.acorn.interpret import JSThrow

    src = "class C { constructor(){ missing(); } }\nnew C();"
    with pytest.raises(JSThrow) as ei:
        run_js(src)
    assert ei.value.js_line == 1
    assert "new C" in ei.value.js_trace


def test_hyperscript_helper_builds_domonic_tree():
    doc, _ = run_js(
        "function h(tag, text, ...kids) {\n"
        "  const el = document.createElement(tag);\n"
        "  if (text) el.textContent = text;\n"
        "  kids.forEach(k => el.appendChild(k));\n"
        "  return el;\n"
        "}\n"
        "document.body.appendChild(\n"
        "  h('div', null, h('h1', 'Title'), h('p', 'body'))\n"
        ");"
    )
    assert str(doc.body) == "<body><div><h1>Title</h1><p>body</p></div></body>"
