"""The tree-walking JS evaluator (`interpret.py`)."""

import pytest

from domonic_libs.acorn.interpret import run_js


def out(src, commonjs=False):
    _doc, lines = run_js(src, commonjs=commonjs)
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


def test_sort_with_a_fractional_comparator():
    # a comparator returning a value between -1 and 1 (e.g. b.v - a.v on two
    # floats less than 1 apart) must not truncate to 0 and leave the pair
    # unsorted -- found via a real-world `procs.js` example sorting by MB.
    assert out(
        "const a = [{v: 187.8}, {v: 188.0}, {v: 96.1}, {v: 221.7}];\n"
        "a.sort((x, y) => y.v - x.v);\n"
        "console.log(a.map(o => o.v).join(','))"
    ) == ["221.7,188,187.8,96.1"]


def test_sloppy_mode_this_defaults_to_the_global_object():
    # a plain (non-arrow) function called with no receiver gets `this` bound
    # to the global object in sloppy mode, not undefined -- the classic
    # `(function(){ this.Foo = ... })()` pattern real-world scripts use to
    # attach a helper to the global scope depends on this.
    assert out("console.log(this === window)") == ["true"]
    assert out(
        "(function(){ this.attachedGlobal = 42; })();\n"
        "console.log(attachedGlobal);"
    ) == ["42"]


def test_classic_prototype_based_inheritance():
    # `function Foo(){}` + `Foo.prototype.bar = ...` -- the pre-ES6 pattern a
    # huge amount of real-world JS (jQuery plugins, older libraries) still
    # uses. `new Foo()` has to link the instance to Foo's *current*
    # prototype object, not a disconnected bare object.
    assert out(
        "function Foo(){}\n"
        "Foo.prototype.bar = function(){ return 42; };\n"
        "console.log(new Foo().bar());"
    ) == ["42"]
    # reassigning .prototype wholesale (the classic base-class-simulation
    # idiom) has to be picked up too, not just mutating the existing object
    assert out(
        "function Foo(){}\n"
        "Foo.prototype = { bar: function(){ return 43; } };\n"
        "console.log(new Foo().bar());"
    ) == ["43"]
    # a method added to the prototype *after* an instance already exists is
    # still visible on it -- proves the link is live, not a one-time copy
    assert out(
        "function Foo(){}\n"
        "const f = new Foo();\n"
        "Foo.prototype.late = function(){ return 'late-ok'; };\n"
        "console.log(f.late());"
    ) == ["late-ok"]


def test_typeof_symbol():
    # Symbols are opaque strings under the hood (see _symbol_ctor) -- without
    # a real typeof case they self-report as "string", and any
    # `typeof x === "symbol"` feature-detection (extremely common in
    # real-world libraries -- this is what broke loading ramda/lodash/
    # mustache/handlebars) silently takes the wrong branch.
    assert out("console.log(typeof Symbol())") == ["symbol"]
    assert out("console.log(typeof Symbol.iterator)") == ["symbol"]
    assert out("console.log(typeof 'a real string')") == ["string"]


def test_object_prototype_to_string_is_a_real_standalone_function():
    # `Object.prototype.toString.call(x)` for robust type-tagging is one of
    # the most common idioms in real-world JS. It needs `Object.prototype`
    # to be a real thing you can grab a *reference* off, and that reference
    # has to read its receiver via `.call`/`.apply`, not whatever it was
    # looked up on.
    assert out("console.log(Object.prototype.toString.call([]))") == ["[object Array]"]
    assert out("console.log(Object.prototype.toString.call(null))") == ["[object Null]"]
    assert out("console.log(Object.prototype.toString.call(42))") == ["[object Number]"]


def test_builtin_prototypes_delegate_to_real_per_type_methods():
    # `Array`/`String`/`RegExp`/... have no real `.prototype` of their own
    # (interpreter functions and domonic classes, not authored-in-JS
    # classes) -- but real-world code commonly borrows a method as a
    # standalone reference first: `var test = RegExp.prototype.test; test
    # .call(re, str)` (this exact pattern broke loading mustache.min.js).
    assert out(
        "var test = RegExp.prototype.test;\n"
        "console.log(test.call(/\\S/, 'hi'));"
    ) == ["true"]
    assert out(
        "var slice = Array.prototype.slice;\n"
        "console.log(JSON.stringify(slice.call([1,2,3,4], 1, 3)));"
    ) == ["[2,3]"]


def test_static_property_assigned_after_class_declaration():
    # `SomeClass.create = (params) => ...`, attached *outside* the class
    # body after the fact -- a real, common pattern (this is exactly how
    # zod attaches its schema factories: `ZodString.create = (params) => new
    # ZodString(...)`). The write has to land where `js_get`'s JSClass
    # branch actually looks (`.statics`), not as an inert Python attribute.
    assert out(
        "class Foo {}\n"
        "Foo.create = (x) => x * 2;\n"
        "console.log(Foo.create(21));"
    ) == ["42"]


def test_class_extending_a_native_error_class():
    # `class MyError extends Error { constructor(msg) { super(msg); ... } }`
    # -- extending a real native/domonic class, not one authored in JS. This
    # used to crash the interpreter outright (`AttributeError`/`KeyError`
    # walking a superclass chain that assumed every link was a JSClass);
    # now it should not crash, and `super(msg)` should actually forward the
    # message to the real Error base.
    assert out(
        "class MyError extends Error {\n"
        "  constructor(msg) { super(msg); this.name = 'MyError'; }\n"
        "}\n"
        "let r;\n"
        "try { throw new MyError('oops'); }\n"
        "catch (e) { r = [e.name, e.message, e instanceof Error].join(','); }\n"
        "console.log(r);"
    ) == ["MyError,oops,true"]


def test_labeled_statement_nested_inside_a_plain_loop():
    # a real parser bug, not an interpreter one: an unlabeled loop pushes a
    # nameless sentinel (`_loopLabel = {"kind": "loop"}`) onto the parser's
    # label stack to track break/continue validity; matching a labeled
    # `continue` against it did *strict* dict indexing (`label["name"]`)
    # instead of a safe lookup, so a labeled statement nested inside a plain
    # loop crashed the parser outright with a raw KeyError (this is exactly
    # what broke parsing d3.min.js).
    assert out(
        "let out = [];\n"
        "for (let i = 0; i < 2; i++) {\n"
        "  outer: for (let j = 0; j < 2; j++) {\n"
        "    if (j === 1) continue outer;\n"
        "    out.push(i + ',' + j);\n"
        "  }\n"
        "}\n"
        "console.log(out.join('|'));"
    ) == ["0,0|1,0"]


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


def test_typed_array_indexed_assignment_writes_the_real_buffer():
    # `u[0] = 66` on a Uint8Array (or any array-like Python object with a
    # real __getitem__/__setitem__) has to go through those, not the generic
    # setattr fallback -- otherwise it silently creates an attribute
    # literally named "0" and the backing buffer is never actually touched
    # (reads still "worked" by reading that same shadow attribute back,
    # which is what made this easy to miss -- so check the real buffer too).
    _doc, log = run_js(
        "const u = new Uint8Array(3);\n"
        "u[0] = 66; u[1] = 77; u[2] = 255;\n"
        "console.log(u[0], u[1], u[2], u.length);\n"
        "console.log(u.buffer.tobytes().hex());\n"
    )
    assert log == ["66 77 255 3", "424dff"]


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
    assert ei.value.value.name == "TypeError"


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


def test_named_function_expression_can_recurse():
    assert out(
        "const fact = function f(n) { return n <= 1 ? 1 : n * f(n - 1); };\n"
        "console.log(fact(5));"
    ) == ["120"]


def test_map_entries_iterate_as_arrays():
    assert out(
        "const m = new Map([['a', 1], ['b', 2]]);\n"
        "console.log(JSON.stringify([...m.entries()]));\n"
        "console.log([...m].map(([k, v]) => k + v).join(','));"
    ) == ['[["a",1],["b",2]]', "a1,b2"]


def test_custom_symbol_iterator():
    assert out(
        "const range = { from: 1, to: 4, [Symbol.iterator]() {\n"
        "  let c = this.from; const end = this.to;\n"
        "  return { next: () => c <= end ? { value: c++, done: false } : { done: true } };\n"
        "} };\n"
        "console.log([...range].join(','));\n"
        "let s = 0; for (const n of range) s += n; console.log(s);"
    ) == ["1,2,3,4", "10"]


def test_destructuring_assignment_to_member_targets():
    assert out(
        "const a = [3, 1, 2];\n"
        "[a[0], a[2]] = [a[2], a[0]];\n"
        "console.log(a.join(','));\n"
        "const o = {}; [o.x, o.y] = [1, 2]; console.log(o.x, o.y);"
    ) == ["2,1,3", "1 2"]


def test_for_of_over_infinite_generator_with_break():
    assert out(
        "function* naturals() { let n = 1; while (true) yield n++; }\n"
        "const out = [];\n"
        "for (const x of naturals()) { out.push(x); if (out.length === 5) break; }\n"
        "console.log(out.join(','));"
    ) == ["1,2,3,4,5"]


def test_string_iterates_by_code_point():
    assert out(
        "console.log('a\\u{1F600}b'.length, [...'a\\u{1F600}b'].length);"
    ) == ["4 3"]


def test_generator_method_with_computed_symbol_key():
    assert out(
        "class R { constructor(a, b) { this.a = a; this.b = b; } "
        "*[Symbol.iterator]() { for (let i = this.a; i < this.b; i++) yield i; } }\n"
        "console.log([...new R(2, 6)].join(','));"
    ) == ["2,3,4,5"]


def test_tagged_template_raw_strings():
    assert out(
        r"console.log(String.raw`a\n${1}b`);"
        "\nfunction t(s, ...v) { return s.raw.join('|'); }\n"
        r"console.log(t`x\t${0}y`);"
    ) == ["a\\n1b", "x\\t|y"]


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
    assert err.value.name == "TypeError"
    assert "at b → a → <script> (line 2)" in err.value.stack


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


def test_object_define_property_getter_on_a_fresh_plain_object():
    # `getattr(o, "_accessors", None)` never actually falls back to `None`
    # here -- `JSObject.__getattr__` returns UNDEFINED (never raises) for a
    # missing key, so the `None` default of plain `getattr` is unreachable
    # and `.setdefault` crashed on `_Undefined` for every fresh object (this
    # is what broke loading axios/katex/marked/nunjucks and 4 others).
    assert out(
        "const o = {};\n"
        "Object.defineProperty(o, 'x', { get() { return 42; } });\n"
        "console.log(o.x);"
    ) == ["42"]


def test_object_assign_onto_a_function():
    # `Object.assign(target, ...)` assumed `target` is always a real dict
    # (`target.update(s)`); `Object.assign(someFunction, {...})` is real code
    # (this exact pattern is how hammerjs/sortablejs/voca attach properties
    # to a function), and crashed with `'JSFunction' object has no attribute
    # 'update'`.
    assert out(
        "function Foo(){}\n"
        "Object.assign(Foo, { bar: 42, baz: function(){ return 99; } });\n"
        "console.log(Foo.bar, Foo.baz());"
    ) == ["42 99"]


def test_stringify_a_native_class_used_as_a_value():
    # `_stringify`'s callable branch assumed `v` was always a JS function
    # instance, whose bound `__repr__` takes no extra args; a native class
    # exposed as a JS global (`ArrayBuffer`, `DataView`, ...) is callable
    # too, but `getattr(ArrayBuffer, "__repr__")` returns the *unbound*
    # `object.__repr__`, and calling it with no args crashed with
    # "missing 1 required positional argument: 'self'" (this is what broke
    # loading underscore.js, feature-detecting `typeof ArrayBuffer`/
    # `String(DataView)`).
    assert out("console.log(String(ArrayBuffer).indexOf('function') === 0)") == ["true"]


def test_unbound_native_instance_method_via_class_is_not_a_crash():
    # `Function.toString.call(fn)` is a common borrowed-method feature
    # check (this is what broke loading luxon); `Function.toString`
    # (accessed directly on the class, no instance) used to resolve to the
    # real, *unbound* `Object.toString` and crash on a bare call with
    # "missing 1 required positional argument: 'self'". It now resolves
    # through the generic per-type prototype instead (mirroring real JS,
    # where every function inherits from `Function.prototype`), so calling
    # it is safe even though it isn't a literal transcription of the
    # function's source.
    assert out(
        "function f(){}\n"
        "console.log(typeof Function.toString.call(f));"
    ) == ["string"]


def test_native_staticmethod_still_callable_via_class():
    # guards the fix above from over-reaching: `Math.sqrt` is a real
    # `@staticmethod`, and `getattr(Math, 'sqrt')` unwraps to a plain
    # function -- indistinguishable *by shape* from an unbound instance
    # method -- so the crash guard must tell them apart by how the class
    # itself declared the attribute, not just "is it a plain function".
    # Getting this wrong once made every `Math.*` call inside a class
    # method return undefined instead of a number.
    assert out(
        "class Point {\n"
        "  constructor(x, y) { this.x = x; this.y = y; }\n"
        "  dist() { return Math.sqrt(this.x * this.x + this.y * this.y); }\n"
        "}\n"
        "console.log(new Point(3, 4).dist());"
    ) == ["5"]


def test_var_inside_a_for_loop_is_function_scoped():
    # `var` is function-scoped in real JS, not block-scoped: a `var`
    # declared inside a `for(...)` init (or any `{ }` block) must land in
    # the nearest enclosing function, not the loop's own throwaway
    # Environment -- otherwise it vanishes once the loop ends, and a later
    # reference in the same function resolves to an unrelated *outer*
    # variable of the same name instead of the one the loop just built.
    # This is exactly what broke loading luxon: `for(var e=.., t=new
    # Array(e), n=0; ...) t[n]=...` left the function's own `t` invisible
    # right after the loop, silently falling back to an outer `t` (a regex,
    # in luxon's case) and crashing with "undefined is not a function"
    # -- or worse, running on, but against the wrong value.
    assert out(
        "var t = 'outer';\n"
        "function build(n) {\n"
        "  for (var i = 0, t = new Array(n), j = 0; j < n; j++) t[j] = j + 1;\n"
        "  return t;\n"
        "}\n"
        "console.log(build(3).join(','), t);"
    ) == ["1,2,3 outer"]


def test_object_is_directly_callable():
    # `Object` was a plain namespace dict (`Object.keys`, `.assign`, ...) with
    # no `__call__` of its own; real JS `Object` is *also* a constructor you
    # can call directly (`Object(value)` -- a common defensive-coercion
    # idiom used by lodash/handlebars/fuse.js to box a value, or return a
    # fresh empty object for `null`/`undefined`), and calling it crashed with
    # "[object Object] is not a function".
    assert out(
        "var x = {a: 1};\n"
        "console.log(Object(x) === x, typeof Object(null), typeof Object.keys);"
    ) == ["true object function"]


def test_string_property_is_enumerable_for_a_valid_index():
    # `"z".propertyIsEnumerable(0)` -- a classic ES5-shim feature check
    # (lodash/handlebars use it to decide whether they need an
    # `Object.keys` polyfill for boxed strings) -- came back `undefined`
    # since plain strings had no such method, and calling `undefined` as a
    # function crashed loading handlebars.
    assert out(
        "console.log('z'.propertyIsEnumerable(0), 'z'.propertyIsEnumerable(5));"
    ) == ["true false"]


def test_borrowed_method_call_on_a_receiver_without_it_is_a_real_typeerror():
    # `SomeCtor.prototype.aMethodItDoesntHave` is deliberately permissive
    # (see `_GenericPrototype`) so a genuinely borrowed method -- `var t =
    # RegExp.prototype.test; t.call(re, s)` -- still resolves once the real
    # receiver shows up via `.call`/`.apply`. But when that receiver's own
    # type truly doesn't have the method either, resolution lands on
    # `undefined`, and calling *that* used to crash with a raw Python
    # "'_Undefined' object is not callable" instead of a real JS TypeError
    # (this is what broke loading handlebars, past its `Object()` fix).
    from domonic_libs.acorn.interpret import JSThrow

    with pytest.raises(JSThrow) as ei:
        out("Function.prototype.aMadeUpMethodNumberOneOnly.call(5);")
    assert "is not a function" in str(ei.value)


def test_string_and_number_delegate_to_domonic_javascript():
    # `String()`/`Number()` used to return a bare Python `str`/coerced number
    # computed entirely by the interpreter's own `_stringify`/`js_number`.
    # domonic 1.7 made `domonic.javascript.String`/`Number` real `str`/`float`
    # *subclasses* (not the disconnected wrapper object they used to be), so
    # the interpreter now wraps its own (sentinel-aware) coercion in
    # domonic's real classes instead, matching how `Math`/`Error` were
    # migrated onto domonic in 1.6.
    assert out(
        "console.log(typeof String(5), String(5) === '5', String(5) + '!');\n"
        "console.log(typeof Number('5'), Number('5') === 5, Number(5) + 1);"
    ) == ["string true 5!", "number true 6"]


def test_json_stringify_a_wrapped_number_has_no_trailing_dot_zero():
    # `domonic.javascript.Number` is a `float` *subclass*, so even a whole
    # number stays float-backed at the C level once `String()`/`Number()`
    # started wrapping their result in it -- Python's stdlib `json` module
    # (which the interpreter's own `JSON.stringify` uses under the hood)
    # would otherwise render it with a trailing ".0", and leave `NaN`/
    # `Infinity` as literal (invalid-JSON) tokens instead of `null`.
    assert out(
        "console.log(JSON.stringify({a: Number(5), b: 5.5, c: NaN, d: Infinity}));"
    ) == ['{"a":5,"b":5.5,"c":null,"d":null}']


def test_two_interpreters_dispatch_correctly_side_by_side():
    # `evaluate`/`execute` used to look up `_ex_<Type>`/`_st_<Type>` via
    # `getattr(self, ...)`, returning a method already *bound* to that one
    # `Interpreter` instance; a benchmarking pass replaced that per-call
    # string-concat-plus-getattr with a single dict lookup keyed by node
    # type -- but the dict has to store the *unbound* function and take
    # `self` explicitly at call time, or two separate `Interpreter`
    # instances running side by side (a real pattern -- `default_globals()`
    # is called fresh per real-world-sweep library, per REPL session, ...)
    # would silently share one instance's bound methods.
    from domonic_libs.acorn.interpret import Interpreter, default_globals

    g1, c1, d1, w1 = default_globals()
    i1 = Interpreter(g1, global_object=w1)
    g2, c2, d2, w2 = default_globals()
    i2 = Interpreter(g2, global_object=w2)

    i1.run("var x = 1;")
    i2.run("var x = 2;")
    assert i1.run("x") == 1
    assert i2.run("x") == 2


def test_commonjs_is_opt_in_not_default():
    # `module`/`exports`/`require` are NOT present unless explicitly asked
    # for -- a real browser has none of the three either, and *merely their
    # presence* (never mind whether a script ever calls `require`) flips
    # which branch a UMD bundle's own environment check takes
    # (`typeof module !== "undefined" ? module.exports = ... : window.Lib =
    # ...`), silently losing the global almost every real-world library
    # (lodash, dayjs, chroma, Mustache, zod, ...) exposes itself as. This
    # was a real regression caught by re-running the `realworld` sweep after
    # first making these on by default.
    assert out(
        "console.log(typeof module, typeof exports, typeof require);"
    ) == ["undefined undefined undefined"]


def test_commonjs_module_exports_and_require(tmp_path):
    # a real, big cluster of real-world bundles are plain CommonJS, not
    # browser UMD -- found via the `domonic_libs.realworld` sweep, where
    # roughly half of all load failures were exactly `require`/`module`/
    # `exports is not defined`. ES modules (`import`/`export`) were already
    # a core interpreter feature, not something bolted onto `myjs`; this
    # gives CommonJS the same treatment, opt-in via `commonjs=True` (see
    # `test_commonjs_is_opt_in_not_default` for why it isn't the default).
    assert out(
        "console.log(typeof module, typeof exports, typeof require);",
        commonjs=True,
    ) == ["object object function"]

    # `exports.x = y` mutates the *same* object `module.exports` starts as
    # (aliased, not copied) -- but reassigning `module.exports` wholesale
    # breaks that link, exactly like real Node.
    assert out("exports.bar = 99; console.log(module.exports.bar);", commonjs=True) == ["99"]

    (tmp_path / "math_util.js").write_text(
        "exports.double = function(x) { return x * 2; };\n"
        "module.exports.PI_ISH = 3.14;\n"
    )
    path = str(tmp_path / "math_util.js").replace("\\", "\\\\")
    assert out(
        f'var m = require("{path}");\n'
        "console.log(m.double(21), m.PI_ISH);",
        commonjs=True,
    ) == ["42 3.14"]

    # a bare specifier resolves to a real Python module, the same
    # convention `import x from "some_python_module"` already uses.
    assert out('console.log(typeof require("os").getcwd);', commonjs=True) == ["function"]

    # a genuinely missing module is a clean JS error, not a raw traceback.
    from domonic_libs.acorn.interpret import JSThrow
    with pytest.raises(JSThrow) as ei:
        out('require("/does/not/exist.js");', commonjs=True)
    assert "cannot find module" in str(ei.value)


def test_commonjs_require_caches_and_tolerates_circular_requires(tmp_path):
    (tmp_path / "a.js").write_text(
        "module.exports.fromA = 1;\n"
        "module.exports.b = require('./b.js');\n"
    )
    (tmp_path / "b.js").write_text(
        # `a.js` is still mid-execution (its `module.exports` only has
        # `fromA` so far) -- a real `require('./a.js')` here would see
        # that partial object, not crash or infinite-loop.
        "var a = require('./a.js');\n"
        "module.exports.sawFromA = a.fromA;\n"
    )
    path = str(tmp_path / "a.js").replace("\\", "\\\\")
    assert out(f'var a = require("{path}"); console.log(a.b.sawFromA);', commonjs=True) == ["1"]


def test_math_cbrt_log_are_correctly_rounded_for_exact_cases():
    # Python's `math` is backed by the platform libm, and glibc's `cbrt(27)`
    # is `3.0000000000000004` (a ULP high) where V8 gives exactly `3` -- this
    # failed CI on Linux but not macOS. `_make_math_ns` snaps the
    # provably-exact integer cases back; irrational results are untouched, and
    # every other `Math` method passes straight through to domonic's.
    assert out(
        "console.log("
        "  Math.cbrt(27) === 3, Math.cbrt(-8) === -2, Math.cbrt(64) === 4,"
        "  Math.log2(8) === 3, Math.log2(1024) === 10,"
        "  Math.log10(1000) === 3, Math.log10(1e6) === 6"
        ");"
    ) == ["true true true true true true true"]
    # not a perfect cube / power -> left alone
    assert out("console.log(Math.cbrt(2) > 1.259 && Math.cbrt(2) < 1.26)") == ["true"]
    assert out("console.log(Math.sqrt(144), Math.pow(2, 10), Math.max(1, 9, 3))") == ["12 1024 9"]
