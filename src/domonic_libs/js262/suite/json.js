// JSON.parse / JSON.stringify. Mirrors built-ins/JSON/*.

test262("stringify primitives", function () {
  assert.sameValue(JSON.stringify(1), "1");
  assert.sameValue(JSON.stringify("x"), '"x"');
  assert.sameValue(JSON.stringify(true), "true");
  assert.sameValue(JSON.stringify(null), "null");
  assert.sameValue(JSON.stringify(undefined), undefined);
});

test262("stringify arrays and objects", function () {
  assert.sameValue(JSON.stringify([1, 2, 3]), "[1,2,3]");
  assert.sameValue(JSON.stringify({ a: 1, b: 2 }), '{"a":1,"b":2}');
  assert.sameValue(JSON.stringify({ a: [1, { b: 2 }] }), '{"a":[1,{"b":2}]}');
});

test262("stringify skips undefined and functions in objects", function () {
  assert.sameValue(JSON.stringify({ a: 1, b: undefined, c: function () {} }), '{"a":1}');
  assert.sameValue(JSON.stringify([1, undefined, 2]), "[1,null,2]");
});

test262("stringify with indent", function () {
  assert.sameValue(JSON.stringify({ a: 1 }, null, 2), '{\n  "a": 1\n}');
});

test262("parse primitives and structures", function () {
  assert.sameValue(JSON.parse("1"), 1);
  assert.sameValue(JSON.parse('"x"'), "x");
  assert.sameValue(JSON.parse("true"), true);
  assert.sameValue(JSON.parse("null"), null);
  assert.compareArray(JSON.parse("[1,2,3]"), [1, 2, 3]);
  assert.sameValue(JSON.parse('{"a":1}').a, 1);
  assert.sameValue(JSON.parse('{"a":{"b":[1,2]}}').a.b[1], 2);
});

test262("round-trip", function () {
  var value = { name: "test", nums: [1, 2, 3], nested: { ok: true }, s: "a\nb" };
  assert.sameValue(JSON.stringify(JSON.parse(JSON.stringify(value))), JSON.stringify(value));
});

test262("parse throws SyntaxError on malformed input", function () {
  assert.throws(SyntaxError, function () { JSON.parse("{"); });
  assert.throws(SyntaxError, function () { JSON.parse("{a:1}"); });
  assert.throws(SyntaxError, function () { JSON.parse("[1,2,]"); });
  assert.throws(SyntaxError, function () { JSON.parse(""); });
});

test262("stringify escapes control characters", function () {
  assert.sameValue(JSON.stringify("a\tb"), '"a\\tb"');
  assert.sameValue(JSON.stringify('quote"here'), '"quote\\"here"');
});

test262("parse with a reviver", function () {
  var o = JSON.parse('{"a":1,"b":2}', function (k, v) {
    return typeof v === "number" ? v * 10 : v;
  });
  assert.sameValue(o.a, 10);
  assert.sameValue(o.b, 20);
});

test262("stringify with a replacer function", function () {
  var s = JSON.stringify({ a: 1, b: 2 }, function (k, v) {
    return k === "b" ? undefined : v;
  });
  assert.sameValue(s, '{"a":1}');
});
