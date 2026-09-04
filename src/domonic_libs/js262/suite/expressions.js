// Language expressions: operator precedence, optional chaining, nullish,
// spread, destructuring, template literals, exponentiation, comma.

test262("operator precedence", function () {
  assert.sameValue(1 + 2 * 3, 7);
  assert.sameValue((1 + 2) * 3, 9);
  assert.sameValue(2 ** 3 ** 2, 512);        // right associative
  assert.sameValue(-(2 ** 2), -4);
  assert.sameValue(10 % 3 + 1, 2);
  assert.sameValue(true || false && false, true);
});

test262("exponentiation operator", function () {
  assert.sameValue(2 ** 10, 1024);
  assert.sameValue(2 ** -1, 0.5);
  var x = 3; x **= 2;
  assert.sameValue(x, 9);
});

test262("optional chaining", function () {
  var o = { a: { b: 2 } };
  assert.sameValue(o?.a?.b, 2);
  assert.sameValue(o?.x?.y, undefined);
  assert.sameValue(o?.x?.y ?? "default", "default");
  var fn = null;
  assert.sameValue(fn?.(), undefined);
  assert.sameValue(o?.["a"]?.["b"], 2);
});

test262("nullish coalescing", function () {
  assert.sameValue(null ?? "a", "a");
  assert.sameValue(undefined ?? "a", "a");
  assert.sameValue(0 ?? "a", 0);
  assert.sameValue("" ?? "a", "");
  assert.sameValue(false ?? "a", false);
});

test262("logical assignment", function () {
  var a = null; a ??= 5; assert.sameValue(a, 5);
  var b = 1; b ??= 9; assert.sameValue(b, 1);
  var c = 0; c ||= 7; assert.sameValue(c, 7);
  var d = 2; d &&= 3; assert.sameValue(d, 3);
});

test262("array spread", function () {
  var a = [1, 2];
  var b = [0, ...a, 3];
  assert.compareArray(b, [0, 1, 2, 3]);
  assert.compareArray([...[1], ...[2, 3]], [1, 2, 3]);
  function sum() { var t = 0; for (var i = 0; i < arguments.length; i++) t += arguments[i]; return t; }
  assert.sameValue(sum(...[1, 2, 3, 4]), 10);
});

test262("object spread", function () {
  var a = { x: 1, y: 2 };
  var b = { ...a, z: 3 };
  assert.sameValue(b.x, 1);
  assert.sameValue(b.z, 3);
  var c = { ...a, x: 9 };
  assert.sameValue(c.x, 9);
});

test262("array destructuring", function () {
  var [a, b, ...rest] = [1, 2, 3, 4, 5];
  assert.sameValue(a, 1);
  assert.sameValue(b, 2);
  assert.compareArray(rest, [3, 4, 5]);
  var [, second] = [10, 20];
  assert.sameValue(second, 20);
  var [x = 7, y = 8] = [1];
  assert.sameValue(x, 1);
  assert.sameValue(y, 8);
});

test262("object destructuring", function () {
  var { a, b: renamed, c = 3 } = { a: 1, b: 2 };
  assert.sameValue(a, 1);
  assert.sameValue(renamed, 2);
  assert.sameValue(c, 3);
  var { x, ...others } = { x: 1, y: 2, z: 3 };
  assert.sameValue(x, 1);
  assert.sameValue(others.y, 2);
  assert.sameValue(others.z, 3);
});

test262("nested destructuring", function () {
  var { a: { b: [first] } } = { a: { b: [42] } };
  assert.sameValue(first, 42);
});

test262("swap via destructuring", function () {
  var a = 1, b = 2;
  [a, b] = [b, a];
  assert.sameValue(a, 2);
  assert.sameValue(b, 1);
});

test262("template literals", function () {
  var name = "world";
  assert.sameValue(`hello ${name}`, "hello world");
  assert.sameValue(`${1 + 2} = 3`, "3 = 3");
  assert.sameValue(`a
b`, "a\nb");
  assert.sameValue(`${`nested ${name}`}`, "nested world");
});

test262("tagged template literal", function () {
  function tag(strings) {
    var out = strings[0];
    for (var i = 1; i < arguments.length; i++) out += "[" + arguments[i] + "]" + strings[i];
    return out;
  }
  assert.sameValue(tag`a${1}b${2}c`, "a[1]b[2]c");
});

test262("comma operator", function () {
  var x = (1, 2, 3);
  assert.sameValue(x, 3);
});

test262("conditional (ternary)", function () {
  assert.sameValue(1 ? "a" : "b", "a");
  assert.sameValue(0 ? "a" : "b", "b");
  assert.sameValue(1 ? 0 ? "x" : "y" : "z", "y");
});

test262("increment / decrement", function () {
  var i = 5;
  assert.sameValue(i++, 5);
  assert.sameValue(i, 6);
  assert.sameValue(++i, 7);
  assert.sameValue(i--, 7);
  assert.sameValue(i, 6);
});

test262("in and instanceof", function () {
  assert.sameValue("a" in { a: 1 }, true);
  assert.sameValue("b" in { a: 1 }, false);
  assert.sameValue(0 in [1, 2], true);
  assert.sameValue([] instanceof Array, true);
  assert.sameValue((function () {}) instanceof Function, true);
});
