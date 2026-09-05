# domonic.javascript wrinkles

Where [`docs/domonic-wrinkles.md`](domonic-wrinkles.md) tracks the DOM, this file tracks `domonic.javascript` -- the runtime shim (`String`, `Array`, `Number`, `RegExp`, `Math`, ...) that every port in this repo stands on. It is stress-tested by porting [acorn](https://github.com/acornjs/acorn) and by a curated test262-style battery run through the interpreter (`python -m domonic_libs.js262`, scorecard in [`docs/js-compliance.md`](js-compliance.md)).

The battery is at **100%** (175/175). **domonic 1.6 and 1.7 closed nearly all of this list** (see *Resolved* below); the interpreter deleted its `Math` and `Error` shims in 1.6, and its `String` / `Number` ones in 1.7 (once domonic 1.7 made them real `str` / `float` subclasses), and now delegates all four to `domonic.javascript` -- `Math` through a thin wrapper that only fixes libm rounding (below), the rest outright. (`Object`, `JSON`, and `Array.from` were never shimmed the same way -- the interpreter has always had its own independent implementations of those, so domonic 1.7 fixing the matching `domonic.javascript` gaps helps anyone using `domonic.javascript` directly, without changing the interpreter.) Verified against **published `domonic 1.7.0`**. What's left: `Boolean` still ships its own interpreter version (Python can't subclass `bool`), a narrow `Map` key gap, a `domonic.javascript`-direct `String.fromCodePoint` nuance, and `Math.cbrt`/`log2`/`log10` platform-libm rounding (worked around).

## 1. `String()` / `Number()` return wrapper objects -- substantially narrowed, `Boolean()` still fully open

1.7.0 made `domonic.javascript.String` a real **`str` subclass** and `Number` a real **`float` subclass** (`12561b4`) -- missed in this file until now -- which closes most of what this wrinkle used to describe:

```python
from domonic.javascript import String, Number, JSON
s, n = String(5), Number(5)
isinstance(s, str), isinstance(n, float)   # True, True -- was False, False
s + "!", n + 1                             # "5!", 6 -- arithmetic/concatenation just works
{s: 1}.get("5")                            # 1 -- dict-key-matches a real string
JSON.stringify({"x": n})                   # '{"x":5}' -- domonic's own JSON.stringify
                                            # normalises the trailing ".0" away (a separate,
                                            # newer fix); Python's stdlib json.dumps does not.
```

What's left is a narrow, rarely-hit residue: `type(s) is str` is still `False` (`type(s).__name__` is still `"String"`), and Python's stdlib `json.dumps` (not domonic's own `JSON.stringify`) still renders a `Number` as `5.0`. `Boolean` gets none of this -- Python cannot subclass `bool` at all, so `isinstance(Boolean(0), bool)` is `False` and `json.dumps` refuses to serialise it outright, though it does carry a correct `__eq__` / `__bool__` / `__str__` (`Boolean(0) == False`, falsy in an `if`, `str(...)` -> `"false"`). `Global.String` / `Global.Number` / `Global.Boolean` still return real primitives outright, for anyone who wants to sidestep this entirely.

**The interpreter's `String()` / `Number()` now delegate to `domonic.javascript`'s** (`_make_string_ctor` / `_number_ctor` in `interpret.py`), the same way `Math` and the `Error` family were migrated in 1.6 -- the interpreter's own `_stringify` / `js_number` still do the sentinel-aware coercion first (domonic has no notion of this interpreter's `UNDEFINED`), then the result is wrapped in domonic's real `String` / `Number` rather than handed back as a bare Python `str` / `float`. `Boolean` was **not** migrated -- it still needs its own primitive-coercion path, since Python can't subclass `bool` at all, so a wrapped `Boolean` couldn't act as a real JS primitive boolean the way wrapped `String`/`Number` now can. (1.7 also gave `String`/`Number` `__slots__`, so `s.foo = 1` on one raises -- a real primitive has no attribute slots either, so this is more correct, not less.)

## 1b. `Map` stringifies every key, so `1` and `"1"` collide

```python
from domonic.javascript import Map
m = Map([[1, "a"]])
m[1], m["1"]   # "a", "a"   (JS: m.get(1) === "a", m.get("1") === undefined --
               #             a number key and a string key are different keys)
```

`Map.__init__`/`__setitem__`/`__getitem__` all do `normalized_key = str(key)` before touching `self._dict`, so every key -- a number, `null`, an object, another `Map` -- collapses to its string form. Real JS `Map` keys can be *anything*, compared by SameValueZero for primitives and by reference identity for objects (a very common real-world pattern: a `Map` keyed by DOM nodes or plain objects, not just strings/numbers). An object key would silently become `"<Object object at 0x...>"`-style noise, or worse, every plain-object key collapse onto the same string if `str(obj)` isn't unique per instance. 1.7 fixed the sibling `Set` SameValueZero gap but not this one. Found via `myjs`'s REPL sweep (`_display`'s new `Map`/`Set` formatting surfaced it while testing `new Map([[1, "a"]])`).

## 2. `String.fromCodePoint` with an astral code point (`domonic.javascript`-direct only)

`domonic.javascript.String.fromCodePoint(0x1F600)` returns a bare Python `str`, which is code-point indexed -- `len(...)` is `1`, where JS reports `2` (a UTF-16 surrogate pair). **The interpreter is unaffected**: it has its own UTF-16-aware `String` semantics, so `String.fromCodePoint(0x1F600).length === 2` through `myjs`. This one only bites code using `domonic.javascript.String` directly and depending on the length, and it's arguably unfixable without a UTF-16-backed string type -- minor, left as a known nuance rather than a bug.

## 3. `Math.cbrt` / `log2` / `log10` aren't correctly rounded for exact-integer cases

```python
from domonic.javascript import Math
Math.cbrt(27)   # 3.0000000000000004 on glibc (Linux)   (JS/V8: exactly 3)
```

`domonic.javascript.Math` delegates `cbrt` / `log2` / `log10` to Python's `math`, which is backed by the platform libm. glibc's `cbrt` isn't correctly rounded for all inputs, so `cbrt(27)` comes back a ULP high; macOS's libm and V8 both give exactly `3`. This surfaced as a **CI failure on Linux but not macOS** (`number-math.js`, `Math.cbrt(27) === 3`). **The interpreter works around it** -- `_make_math_ns` in `interpret.py` snaps `cbrt` / `log2` / `log10` back to the correctly-rounded value for the cases where the rounded result provably cubes/exponentiates back to the input (irrational results untouched, every other `Math` method passes straight through). Drop that shim once `domonic.javascript.Math` rounds these itself: the clean upstream fix is `round(r)` when `round(r) ** 3 == x`.

---

## Resolved in domonic 1.7

* **`Object.freeze` actually blocks writes** — `o.a = 2` on a frozen object now raises, and `Object.isFrozen(o)` is `True`. **`Object.assign` is variadic** — `Object.assign({}, {"a": 1}, {"b": 2})` takes any number of sources, not just one.
* **`JSON.stringify` / `JSON.parse` honour the replacer / reviver callback** — a replacer that returns `undefined` for a key now drops it from the output; a reviver's return value now replaces the parsed value, recursively.
* **`String` / `Number` are real `str` / `float` subclasses** (was #1 above) — `isinstance`, arithmetic, concatenation, comparison, and dict-key-matching now all treat `String(5)` / `Number(5)` exactly like the primitive; only an exact `type(x) is str` check still differs. `Boolean` couldn't get the same treatment (Python can't subclass `bool`) and remains its own thing, with correct `__eq__` / `__bool__` / `__str__` but no `isinstance(_, bool)`.
* **`JSON.stringify` normalises whole-number floats and non-finite values** — `JSON.stringify(3.0)` → `"3"` (not `"3.0"`), `NaN` / `Infinity` → `null`, matching JS.
* **`Date.prototype.toISOString()` / `toJSON()` keep the time** (`ba17965`) — `Date(2020,0,1,12,34,56,789).toISOString()` is `"2020-01-01T12:34:56.789Z"` now, not `"2020-01-01"` (this had been tracked here as an open item). Found via `myjs`'s `clipboard.js` example timestamping its output.
* **`Set` de-duplicates a `String()`/`Number()` result against the matching primitive** (`ba17965`, was #1b) — `Set(["a", String("a")]).size` is `1` now, not `2`; `_js_set_same_value_zero` no longer requires an exact `type()` match before comparing value types. This was the gap the `String`/`Number` migration surfaced.

Verified against **published `domonic 1.7.0`**. Still open: `Map` key stringification (#1b), `String.fromCodePoint` (#2, `domonic.javascript`-direct only), and libm rounding for `Math.cbrt`/`log2`/`log10` (#3, worked around in the interpreter). #1 (`String`/`Number` wrappers) is substantially closed and the interpreter now delegates to it.

---

## Resolved in domonic 1.6

Everything the acorn port and the js262 battery flagged before 1.6 — each fixed upstream:

* **The `Error` family** — `TypeError`, `RangeError`, `SyntaxError`, `ReferenceError`, `EvalError`, `URIError`, `AggregateError` all exist as real classes; `.name`, `.message`, `.stack`, `str()` → `"TypeError: msg"`, and `instanceof` all work. *The interpreter now uses these directly and deleted its own error constructors.*
* **`Math.max` / `Math.min` are variadic** and return spec values (`Math.min()` → `Infinity`); the full method set is present. *The interpreter deleted its `Math` shim and delegates to `domonic.javascript.Math`* (later wrapped thinly, see #3, only to fix `cbrt`/`log2`/`log10` libm rounding).
* **`String()` / `Number()` / `Boolean()` coercion** — `String(null)` → `"null"`, `String(true)` → `"true"`, `String([1,2])` → `"1,2"`, `String(5)` → `"5"` (not `"5.0"`); `Boolean(0)` → real `False`; `Global.Number("x")` → NaN float (not the string `"NaN"`); `Global.String()` no-arg → `""`.
* **`Promise` statics** — `Promise.resolve` / `reject` work as statics, plus `all` / `allSettled` / `race` / `any` / `.finally`.
* **Module-level globals** — `isNaN`, `isFinite`, `structuredClone`, `queueMicrotask`, `btoa`, `atob` are all exported.
* **`JSON.parse` throws `SyntaxError`** on malformed input instead of leaking a Python `JSONDecodeError`.
* **`Array(n)` creates `n` empty slots**; `Array.prototype.values()` works; `Number.prototype.toPrecision` renders the exponent JS-style (`1.23e+3`).
* **`parseInt("abc")` returns `NaN`**; **`"x".split("")`** splits into characters instead of raising.
* Earlier (1.5/1.6): static `String.fromCharCode` / `fromCodePoint` / `raw`; `charCodeAt` past-end → numeric NaN; `[^]` / `\u{…}` regex translation; UTF-16 code-unit `String`; `String[i]` past-end → `undefined`.

## Held up well

- `RegExp`: global flag, `.lastIndex`, `.exec`, `.test`, sticky `y`, `\p{...}`, named groups, lookaround, `/` inside a class, `v`-flag class-set operations, and `String.replace` / `match` / `matchAll` / `split` accepting a RegExp with `$1` / `$<name>` expansion.
- `Array` instance methods: `map`, `filter`, `reduce` / `reduceRight`, `flat` / `flatMap`, `find` / `findLast`, `at`, `includes`, `toSorted`, `values` — the interpreter delegates to all of them.
- `String` instance methods: `padStart` / `padEnd`, `at`, `replaceAll`, `normalize`, `localeCompare`, `matchAll`.
- `Object` statics: `keys` / `values` / `entries` / `assign` (two-arg) / `fromEntries` / `getOwnPropertyNames` / `create(null)`.
- `parseInt` / `parseFloat` match JS; Python `int` stands in for `BigInt` *values*.
- The recursive-descent parser and regex-literal validator ports run clean against 1.6.
