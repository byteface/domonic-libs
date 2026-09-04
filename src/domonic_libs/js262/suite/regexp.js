// RegExp: test / exec / match / replace, flags, groups, named groups.
// Mirrors built-ins/RegExp/*.

test262("literal and constructor forms", function () {
  assert.sameValue(/abc/.test("xabcx"), true);
  assert.sameValue(new RegExp("abc").test("xabcx"), true);
  assert.sameValue(new RegExp("a.c", "i").test("XAZC".toLowerCase()), true);
});

test262("test and the i flag", function () {
  assert.sameValue(/hello/i.test("HELLO"), true);
  assert.sameValue(/hello/.test("HELLO"), false);
});

test262("exec returns match and captures", function () {
  var m = /(\d{4})-(\d{2})-(\d{2})/.exec("date: 2024-05-17.");
  assert.sameValue(m[0], "2024-05-17");
  assert.sameValue(m[1], "2024");
  assert.sameValue(m[3], "17");
  assert.sameValue(m.index, 6);
});

test262("global flag and lastIndex", function () {
  var re = /\d/g;
  assert.sameValue(re.exec("a1b2")[0], "1");
  assert.sameValue(re.lastIndex, 2);
  assert.sameValue(re.exec("a1b2")[0], "2");
});

test262("String.match without and with g", function () {
  assert.sameValue("a1b2c3".match(/\d/)[0], "1");
  assert.compareArray("a1b2c3".match(/\d/g), ["1", "2", "3"]);
});

test262("named capture groups", function () {
  var m = /(?<year>\d{4})-(?<month>\d{2})/.exec("2024-05");
  assert.sameValue(m.groups.year, "2024");
  assert.sameValue(m.groups.month, "05");
});

test262("replace with $1 back-references", function () {
  assert.sameValue("2024-05-17".replace(/(\d+)-(\d+)-(\d+)/, "$3/$2/$1"), "17/05/2024");
});

test262("replace with a named group reference", function () {
  assert.sameValue(
    "2024-05".replace(/(?<y>\d{4})-(?<m>\d{2})/, "$<m>/$<y>"),
    "05/2024"
  );
});

test262("replace with a function", function () {
  var out = "a1b2".replace(/(\d)/g, function (whole, digit) { return "<" + digit + ">"; });
  assert.sameValue(out, "a<1>b<2>");
});

test262("character classes and quantifiers", function () {
  assert.sameValue(/^[a-z]+$/.test("hello"), true);
  assert.sameValue(/^[a-z]+$/.test("Hello"), false);
  assert.sameValue(/\bword\b/.test("a word here"), true);
  assert.sameValue(/colou?r/.test("color"), true);
  assert.sameValue(/a{2,3}/.test("aaaa"), true);
});

test262("anchors, alternation, non-greedy", function () {
  assert.sameValue(/^(cat|dog)$/.test("dog"), true);
  assert.sameValue("<a><b>".match(/<.+?>/)[0], "<a>");
  assert.sameValue("<a><b>".match(/<.+>/)[0], "<a><b>");
});

test262("lookahead", function () {
  assert.sameValue(/\d+(?= dollars)/.exec("100 dollars")[0], "100");
  assert.sameValue(/foo(?!bar)/.test("foobaz"), true);
  assert.sameValue(/foo(?!bar)/.test("foobar"), false);
});

test262("unicode property escapes", function () {
  assert.sameValue(/\p{L}/u.test("é"), true);
  assert.sameValue(/\p{N}/u.test("7"), true);
});

test262("split with a regex", function () {
  assert.compareArray("a1b2c3d".split(/\d/), ["a", "b", "c", "d"]);
  assert.compareArray("a, b,c ,  d".split(/\s*,\s*/), ["a", "b", "c", "d"]);
});

test262("flags property", function () {
  assert.sameValue(/x/gi.global, true);
  assert.sameValue(/x/gi.ignoreCase, true);
  assert.sameValue(/x/.global, false);
  assert.sameValue(/x/gim.flags.split("").sort().join(""), "gim");
});
