// Object statics and basic object semantics. Mirrors built-ins/Object/*.

test262("Object.keys / values / entries", function () {
  var o = { a: 1, b: 2, c: 3 };
  assert.compareArray(Object.keys(o).sort(), ["a", "b", "c"]);
  assert.compareArray(Object.values(o).sort(), [1, 2, 3]);
  var e = Object.entries(o).sort((x, y) => x[0] < y[0] ? -1 : 1);
  assert.compareArray(e[0], ["a", 1]);
});

test262("Object.assign", function () {
  var t = Object.assign({}, { a: 1 }, { b: 2 }, { a: 9 });
  assert.sameValue(t.a, 9);
  assert.sameValue(t.b, 2);
  var target = { x: 1 };
  var r = Object.assign(target, { y: 2 });
  assert.sameValue(r, target);
});

test262("Object.fromEntries", function () {
  var o = Object.fromEntries([["a", 1], ["b", 2]]);
  assert.sameValue(o.a, 1);
  assert.sameValue(o.b, 2);
  var round = Object.fromEntries(Object.entries({ x: 10, y: 20 }));
  assert.sameValue(round.y, 20);
});

test262("Object.freeze prevents mutation", function () {
  var o = Object.freeze({ a: 1 });
  try { o.a = 2; } catch (e) {}
  assert.sameValue(o.a, 1);
  assert.sameValue(Object.isFrozen(o), true);
});

test262("Object.create with null prototype", function () {
  var o = Object.create(null);
  o.x = 5;
  assert.sameValue(o.x, 5);
  assert.sameValue("toString" in o, false);
});

test262("property shorthand and computed keys", function () {
  var x = 1, y = 2;
  var o = { x, y, ["k" + "ey"]: 3 };
  assert.sameValue(o.x, 1);
  assert.sameValue(o.key, 3);
});

test262("method shorthand", function () {
  var o = { greet() { return "hi"; } };
  assert.sameValue(o.greet(), "hi");
});

test262("getter / setter in object literal", function () {
  var o = {
    _v: 1,
    get v() { return this._v; },
    set v(x) { this._v = x * 2; }
  };
  assert.sameValue(o.v, 1);
  o.v = 5;
  assert.sameValue(o.v, 10);
});

test262("delete operator", function () {
  var o = { a: 1, b: 2 };
  assert.sameValue(delete o.a, true);
  assert.sameValue("a" in o, false);
  assert.sameValue(o.b, 2);
});

test262("hasOwnProperty", function () {
  var o = { a: 1 };
  assert.sameValue(o.hasOwnProperty("a"), true);
  assert.sameValue(o.hasOwnProperty("toString"), false);
});

test262("JSON round-trips an object", function () {
  var o = { a: [1, 2], b: { c: 3 }, d: "x" };
  assert.sameValue(JSON.stringify(JSON.parse(JSON.stringify(o))), JSON.stringify(o));
});

test262("Object spread does a shallow copy", function () {
  var inner = { n: 1 };
  var o = { inner };
  var copy = { ...o };
  assert.sameValue(copy.inner, inner);
});

test262("computed member access", function () {
  var o = { foo: 1, bar: 2 };
  var k = "foo";
  assert.sameValue(o[k], 1);
  assert.sameValue(o["ba" + "r"], 2);
});

test262("Object.getOwnPropertyNames", function () {
  var o = { a: 1, b: 2 };
  assert.compareArray(Object.getOwnPropertyNames(o).sort(), ["a", "b"]);
});
