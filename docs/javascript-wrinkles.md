# domonic.javascript wrinkles

Where [`docs/domonic-wrinkles.md`](domonic-wrinkles.md) tracks the DOM, this file tracks `domonic.javascript` -- the runtime shim (`String`, `Array`, `Number`, `RegExp`, `Math`, ...) that every port in this repo stands on. It is stress-tested by porting [acorn](https://github.com/acornjs/acorn) and by a curated test262-style battery run through the interpreter (`python -m domonic_libs.js262`, scorecard in [`docs/js-compliance.md`](js-compliance.md)).

The battery sits at **100%** (175/175). The interpreter side of the gap (getters/setters, `Function.prototype.call`/`apply`/`bind`, generators, `eval`, `const` reassignment, UTF-16 string length) is done. What the battery still routes *around* `domonic.javascript` -- because the interpreter ships its own version -- is the list below; closing these lets those shims be deleted so the number reflects domonic directly.

## 5. Missing module-level globals

`isNaN`, `isFinite` (present on `Global`, not exported), `structuredClone`, `queueMicrotask`, `btoa`, `atob`.

## 6. Smaller

* `JSON.parse("{")` raises a Python `JSONDecodeError` (JS: throws `SyntaxError`); `JSON.stringify(undefined)` raises `TypeError: not serializable` (JS: returns `undefined`).
* `parseInt("abc")` does not return `NaN` for an all-garbage string.
* `String.prototype.split("")` raises `ValueError: empty separator` (JS: splits into characters).
* `String.fromCodePoint(0x1F600).length` is 1 (JS: 2 -- an astral code point is two UTF-16 units).
* `Number.prototype.toPrecision` renders the exponent zero-padded (`1.23e+03` vs JS `1.23e+3`).
* `Array.prototype.values` returns `None`.

## Resolved in domonic 1.6

The acorn port surfaced these; each was fixed upstream.

* **`String.fromCharCode` / `fromCodePoint` / `raw` are static.** `String.fromCharCode(65)` is `"A"`; astral recombination works; `String.raw` has the tag signature.
* **`charCodeAt` / `codePointAt` past the end return numeric NaN / `undefined`,** not the string `"NaN"`.
* **`[^]` in a RegExp is rewritten to `[\s\S]`,** including the `\[^]` case.
* **RegExp patterns translate JS `\u{…}` code-point escapes.**
* **`String` models UTF-16 code units** -- `String("a😀b").length` is 4; `charCodeAt(1)` is the lead surrogate. (The *interpreter* still uses Python `str` for its own string values and doesn't yet get this -- an interpreter gap.)
* **`String[i]` past the end yields `undefined`,** not `IndexError`.

## Held up well

- `RegExp`: global flag, `.lastIndex`, `.exec`, `.test`, sticky `y`, `\p{...}`, named groups, lookaround, `/` inside a class, `v`-flag class-set operations -- all behaving, and `String.replace` / `match` / `matchAll` / `split` accept a RegExp and expand `$1` / `$<name>` correctly.
- `Array` instance methods: `map`, `filter`, `reduce` / `reduceRight`, `flat` / `flatMap`, `find` / `findLast`, `at`, `includes`, `toSorted` -- all spec-solid (the interpreter now delegates to them).
- `String` instance methods: `padStart` / `padEnd`, `at`, `replaceAll`, `normalize`, `localeCompare`, `matchAll` -- all present and correct.
- `Object` statics: `keys` / `values` / `entries` / `assign` (two-arg) / `fromEntries` / `freeze` / `create(null)`.
- `parseInt` (radix inference, whitespace, trailing garbage) and `parseFloat` -- match JS. Python `int` stands in for `BigInt` *values*.
- The recursive-descent parser and regex-literal validator ports run clean -- the full front end parses real-world ES2022 modules into ESTree with no `domonic.javascript` gaps.
