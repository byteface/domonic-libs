// Type coercion: String() / Number() / Boolean(), the `+` operator, `==`,
// `typeof`. Mirrors test262 built-ins/String/S15.5.1, built-ins/Number/S15.7.1.

test262("String() with no argument is the empty string", function () {
  assert.sameValue(String(), "");
});

test262("String() of primitives", function () {
  assert.sameValue(String(null), "null");
  assert.sameValue(String(undefined), "undefined");
  assert.sameValue(String(true), "true");
  assert.sameValue(String(false), "false");
  assert.sameValue(String(42), "42");
  assert.sameValue(String(-0), "0");
  assert.sameValue(String(NaN), "NaN");
  assert.sameValue(String(Infinity), "Infinity");
});

test262("String() of objects and arrays", function () {
  assert.sameValue(String([1, 2, 3]), "1,2,3");
  assert.sameValue(String([]), "");
  assert.sameValue(String([null, undefined, 1]), ",,1");
});

test262("String(x) returns a primitive string", function () {
  assert.sameValue(typeof String(5), "string");
  assert.sameValue(typeof String(null), "string");
});

test262("Number() with no argument is 0", function () {
  assert.sameValue(Number(), 0);
});

test262("Number() of primitives", function () {
  assert.sameValue(Number("42"), 42);
  assert.sameValue(Number("  3.5  "), 3.5);
  assert.sameValue(Number(""), 0);
  assert.sameValue(Number(true), 1);
  assert.sameValue(Number(false), 0);
  assert.sameValue(Number(null), 0);
  assert.sameValue(Number("0x10"), 16);
  assert.sameValue(Number([]), 0);
  assert.sameValue(Number([7]), 7);
});

test262("Number() of a non-numeric string is NaN", function () {
  assert.sameValue(Number("nope") !== Number("nope"), true);
  assert.sameValue(Number(undefined) !== Number(undefined), true);
  assert.sameValue(Number([1, 2]) !== Number([1, 2]), true);
});

test262("Number(x) is usable in arithmetic", function () {
  assert.sameValue(Number("7") + 1, 8);
});

test262("Boolean() coercion", function () {
  assert.sameValue(Boolean(), false);
  assert.sameValue(Boolean(0), false);
  assert.sameValue(Boolean(""), false);
  assert.sameValue(Boolean(null), false);
  assert.sameValue(Boolean(undefined), false);
  assert.sameValue(Boolean(NaN), false);
  assert.sameValue(Boolean("x"), true);
  assert.sameValue(Boolean(1), true);
  assert.sameValue(Boolean([]), true);
  assert.sameValue(Boolean({}), true);
});

test262("Boolean(x) returns a primitive boolean", function () {
  assert.sameValue(typeof Boolean(0), "boolean");
  assert.sameValue(Boolean(0) === false, true);
});

test262("the + operator: string concatenation vs addition", function () {
  assert.sameValue(1 + 2, 3);
  assert.sameValue("1" + 2, "12");
  assert.sameValue(1 + "2", "12");
  assert.sameValue([] + [], "");
  assert.sameValue([1] + [2], "12");
  assert.sameValue(1 + null, 1);
  assert.sameValue(1 + undefined !== 1 + undefined, true);   // NaN
  assert.sameValue(true + true, 2);
});

test262("abstract equality ==", function () {
  assert.sameValue(1 == "1", true);
  assert.sameValue(null == undefined, true);
  assert.sameValue(null == 0, false);
  assert.sameValue(0 == false, true);
  assert.sameValue("" == false, true);
  assert.sameValue(NaN == NaN, false);
  assert.sameValue("0" == false, true);
});

test262("strict equality ===", function () {
  assert.sameValue(1 === 1, true);
  assert.sameValue(1 === "1", false);
  assert.sameValue(NaN === NaN, false);
  assert.sameValue(-0 === 0, true);
  assert.sameValue(null === null, true);
});

test262("typeof", function () {
  assert.sameValue(typeof undefined, "undefined");
  assert.sameValue(typeof null, "object");
  assert.sameValue(typeof 1, "number");
  assert.sameValue(typeof "s", "string");
  assert.sameValue(typeof true, "boolean");
  assert.sameValue(typeof {}, "object");
  assert.sameValue(typeof [], "object");
  assert.sameValue(typeof function () {}, "function");
  assert.sameValue(typeof Symbol, "function");
});

test262("unary operators", function () {
  assert.sameValue(+"3", 3);
  assert.sameValue(-"3", -3);
  assert.sameValue(!0, true);
  assert.sameValue(!!"x", true);
  assert.sameValue(~5, -6);
  assert.sameValue(void 0, undefined);
});

test262("String and Number as tag properties", function () {
  assert.sameValue(String.name, "String");
  assert.sameValue(Number.name, "Number");
  assert.sameValue(Boolean.name, "Boolean");
});
