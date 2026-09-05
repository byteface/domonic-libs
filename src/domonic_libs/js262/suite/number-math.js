// Number.prototype, Number statics, Math, parseInt / parseFloat.

test262("Number statics", function () {
  assert.sameValue(Number.isInteger(3), true);
  assert.sameValue(Number.isInteger(3.5), false);
  assert.sameValue(Number.isInteger("3"), false);
  assert.sameValue(Number.isNaN(NaN), true);
  assert.sameValue(Number.isNaN("NaN"), false);
  assert.sameValue(Number.isFinite(3), true);
  assert.sameValue(Number.isFinite(Infinity), false);
  assert.sameValue(Number.isSafeInteger(2 ** 53 - 1), true);
});

test262("Number constants", function () {
  assert.sameValue(Number.MAX_SAFE_INTEGER, 9007199254740991);
  assert.sameValue(Number.MIN_SAFE_INTEGER, -9007199254740991);
  assert.sameValue(Number.POSITIVE_INFINITY, Infinity);
  assert.sameValue(Number.EPSILON > 0, true);
});

test262("Number.prototype methods", function () {
  assert.sameValue((3.14159).toFixed(2), "3.14");
  assert.sameValue((255).toString(16), "ff");
  assert.sameValue((5).toString(2), "101");
  assert.sameValue((1234.5).toPrecision(3), "1.23e+3");
});

test262("parseInt", function () {
  assert.sameValue(parseInt("42"), 42);
  assert.sameValue(parseInt("42px"), 42);
  assert.sameValue(parseInt("0x1F"), 31);
  assert.sameValue(parseInt("11", 2), 3);
  assert.sameValue(parseInt("  -7  "), -7);
  assert.sameValue(parseInt("abc") !== parseInt("abc"), true);   // NaN
});

test262("parseFloat", function () {
  assert.sameValue(parseFloat("3.14"), 3.14);
  assert.sameValue(parseFloat("3.14abc"), 3.14);
  assert.sameValue(parseFloat("1e3"), 1000);
  assert.sameValue(parseFloat(".5"), 0.5);
});

test262("Math rounding", function () {
  assert.sameValue(Math.floor(4.7), 4);
  assert.sameValue(Math.ceil(4.1), 5);
  assert.sameValue(Math.round(4.5), 5);
  assert.sameValue(Math.round(-4.5), -4);
  assert.sameValue(Math.trunc(-4.7), -4);
  assert.sameValue(Math.abs(-9), 9);
  assert.sameValue(Math.sign(-3), -1);
});

test262("Math.max / Math.min", function () {
  assert.sameValue(Math.max(1, 9, 3), 9);
  assert.sameValue(Math.min(4, 2, 8), 2);
  assert.sameValue(Math.max(), -Infinity);
  assert.sameValue(Math.min(), Infinity);
  assert.sameValue(Math.max(...[5, 1, 7]), 7);
});

test262("Math power / roots / logs", function () {
  assert.sameValue(Math.pow(2, 10), 1024);
  assert.sameValue(Math.sqrt(144), 12);
  // cbrt / log2 / log10 land on an exact integer here; the platform libm
  // behind Python's `math` can be a ULP off (glibc's `cbrt(27)` is
  // `3.0000000000000004`), so the interpreter snaps the provably-exact
  // cases back, matching V8. `_make_math_ns` in interpret.py.
  assert.sameValue(Math.cbrt(27), 3);
  assert.sameValue(Math.hypot(3, 4), 5);
  assert.sameValue(Math.log2(8), 3);
  assert.sameValue(Math.log10(1000), 3);
});

test262("Math trig and constants", function () {
  assert.sameValue(Math.abs(Math.sin(0)) < 1e-9, true);
  assert.sameValue(Math.abs(Math.cos(0) - 1) < 1e-9, true);
  assert.sameValue(Math.abs(Math.PI - 3.141592653589793) < 1e-12, true);
  assert.sameValue(Math.abs(Math.E - 2.718281828459045) < 1e-12, true);
});

test262("NaN and Infinity semantics", function () {
  assert.sameValue(NaN === NaN, false);
  assert.sameValue(isNaN(NaN), true);
  assert.sameValue(isFinite(1 / 0), false);
  assert.sameValue(1 / 0, Infinity);
  assert.sameValue(-1 / 0, -Infinity);
  assert.sameValue(0 / 0 !== 0 / 0, true);
});

test262("integer vs float formatting", function () {
  assert.sameValue(String(5), "5");
  assert.sameValue(String(5.0), "5");
  assert.sameValue(String(5.5), "5.5");
  assert.sameValue(`${10 / 2}`, "5");
  assert.sameValue(1e21 + "", "1e+21");
});

test262("bitwise operators", function () {
  assert.sameValue(5 & 3, 1);
  assert.sameValue(5 | 2, 7);
  assert.sameValue(5 ^ 1, 4);
  assert.sameValue(1 << 4, 16);
  assert.sameValue(-8 >> 1, -4);
  assert.sameValue(-8 >>> 28, 15);
});
