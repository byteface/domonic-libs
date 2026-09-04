// String.prototype. Mirrors test262 built-ins/String/prototype/*.

test262("length and indexing", function () {
  assert.sameValue("hello".length, 5);
  assert.sameValue("hello"[0], "h");
  assert.sameValue("hello"[9], undefined);
  assert.sameValue("hello".charAt(1), "e");
  assert.sameValue("hello".charAt(9), "");
});

test262("charCodeAt / codePointAt / fromCharCode", function () {
  assert.sameValue("A".charCodeAt(0), 65);
  assert.sameValue("A".codePointAt(0), 65);
  assert.sameValue("ab".charCodeAt(9) !== "ab".charCodeAt(9), true);   // NaN
  assert.sameValue(String.fromCharCode(72, 105), "Hi");
  assert.sameValue(String.fromCodePoint(0x1F600).length, 2);
});

test262("slice / substring / substr", function () {
  assert.sameValue("hello world".slice(0, 5), "hello");
  assert.sameValue("hello world".slice(-5), "world");
  assert.sameValue("hello".substring(1, 3), "el");
  assert.sameValue("hello".substr(1, 3), "ell");
});

test262("indexOf / lastIndexOf / includes / startsWith / endsWith", function () {
  assert.sameValue("abcabc".indexOf("c"), 2);
  assert.sameValue("abcabc".lastIndexOf("c"), 5);
  assert.sameValue("abc".indexOf("z"), -1);
  assert.sameValue("hello".includes("ell"), true);
  assert.sameValue("hello".startsWith("he"), true);
  assert.sameValue("hello".endsWith("lo"), true);
});

test262("toUpperCase / toLowerCase / trim", function () {
  assert.sameValue("Hello".toUpperCase(), "HELLO");
  assert.sameValue("Hello".toLowerCase(), "hello");
  assert.sameValue("  hi  ".trim(), "hi");
  assert.sameValue("  hi  ".trimStart(), "hi  ");
  assert.sameValue("  hi  ".trimEnd(), "  hi");
});

test262("split", function () {
  assert.compareArray("a,b,c".split(","), ["a", "b", "c"]);
  assert.compareArray("abc".split(""), ["a", "b", "c"]);
  assert.compareArray("a,b,c".split(",", 2), ["a", "b"]);
  assert.compareArray("".split(","), [""]);
});

test262("replace and replaceAll", function () {
  assert.sameValue("a-b-c".replace("-", "+"), "a+b-c");
  assert.sameValue("a-b-c".replaceAll("-", "+"), "a+b+c");
  assert.sameValue("a1b2".replace(/\d/g, "#"), "a#b#");
  assert.sameValue("John Smith".replace(/(\w+)\s(\w+)/, "$2 $1"), "Smith John");
  assert.sameValue("abc".replace(/b/, function (m) { return m.toUpperCase(); }), "aBc");
});

test262("repeat / padStart / padEnd", function () {
  assert.sameValue("ab".repeat(3), "ababab");
  assert.sameValue("5".padStart(3, "0"), "005");
  assert.sameValue("5".padEnd(3, "-"), "5--");
  assert.sameValue("hello".padStart(3), "hello");
});

test262("at", function () {
  assert.sameValue("hello".at(0), "h");
  assert.sameValue("hello".at(-1), "o");
  assert.sameValue("hello".at(99), undefined);
});

test262("concat and template equivalence", function () {
  assert.sameValue("a".concat("b", "c"), "abc");
  assert.sameValue(["a", "b", "c"].join(""), "abc");
});

test262("match / matchAll", function () {
  var m = "the year 2024 and 2025".match(/\d+/g);
  assert.compareArray(m, ["2024", "2025"]);
  var first = "abc123".match(/([a-z]+)(\d+)/);
  assert.sameValue(first[1], "abc");
  assert.sameValue(first[2], "123");
  var all = [...("a1b2c3".matchAll(/([a-z])(\d)/g))];
  assert.sameValue(all.length, 3);
  assert.sameValue(all[1][1], "b");
});

test262("search", function () {
  assert.sameValue("hello world".search(/world/), 6);
  assert.sameValue("hello".search(/z/), -1);
});

test262("normalize is present", function () {
  assert.sameValue(typeof "abc".normalize, "function");
  assert.sameValue("abc".normalize(), "abc");
});

test262("code-unit semantics for astral characters", function () {
  var s = "a\u{1F600}b";
  assert.sameValue(s.length, 4);
  assert.sameValue(s.charCodeAt(1), 0xD83D);
  assert.sameValue(s.slice(0, 1), "a");
});

test262("localeCompare", function () {
  assert.sameValue("a".localeCompare("b") < 0, true);
  assert.sameValue("b".localeCompare("a") > 0, true);
  assert.sameValue("a".localeCompare("a"), 0);
});
