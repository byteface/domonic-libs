// Element.classList (DOMTokenList). WPT: dom/nodes/Element-classlist.html.
// https://dom.spec.whatwg.org/#interface-domtokenlist

function el() { return document.createElement("div"); }

test(function () {
  var e = el();
  e.classList.add("a");
  assert_equals(e.className, "a", "add reflects into className");
  assert_equals(e.classList.length, 1);
  assert_true(e.classList.contains("a"));
}, "add() a single token");

test(function () {
  var e = el();
  e.classList.add("a", "b", "c");
  assert_equals(e.className, "a b c", "add() is variadic");
}, "add() multiple tokens");

test(function () {
  var e = el();
  e.classList.add("a", "b", "c");
  e.classList.remove("b");
  assert_equals(e.className, "a c");
}, "remove() a token");

test(function () {
  var e = el();
  assert_true(e.classList.toggle("d"), "toggle returns true when it adds");
  assert_true(e.classList.contains("d"));
  assert_false(e.classList.toggle("d"), "toggle returns false when it removes");
  assert_false(e.classList.contains("d"));
}, "toggle() without force");

test(function () {
  var e = el();
  assert_true(e.classList.toggle("e", true));
  assert_true(e.classList.toggle("e", true), "toggle(token, true) is idempotent");
  assert_true(e.classList.contains("e"));
}, "toggle() with force=true");

test(function () {
  var e = el();
  e.classList.add("a", "b");
  assert_false(e.classList.toggle("a", false), "toggle(token, false) removes");
  assert_false(e.classList.contains("a"));
}, "toggle() with force=false");

test(function () {
  var e = el();
  e.classList.add("a", "b");
  assert_true(e.classList.replace("a", "z"), "replace returns true when it replaced");
  assert_equals(e.className, "z b", "replace keeps token order");
}, "replace() an existing token");

test(function () {
  var e = el();
  e.classList.add("a");
  assert_false(e.classList.replace("missing", "z"), "replace returns false when token absent");
}, "replace() a missing token");

test(function () {
  var e = el();
  e.classList.add("a", "b", "c");
  assert_equals(e.classList.item(0), "a");
  assert_equals(e.classList.item(1), "b");
  assert_equals(e.classList.item(9), null, "item() past the end is null");
}, "item()");

test(function () {
  var e = el();
  e.classList.add("a", "b");
  assert_equals(e.classList.value, "a b", "value getter is the whole token string");
  assert_equals(String(e.classList), "a b", "stringifier matches value");
}, "value getter and stringifier");

test(function () {
  var e = el();
  e.className = "p q r";
  assert_equals(e.classList.length, 3, "classList reflects an assigned className");
  assert_true(e.classList.contains("q"));
}, "classList reflects className writes");

test(function () {
  var e = el();
  e.classList.add("x");
  e.classList.remove("x");
  assert_equals(e.classList.length, 0);
  assert_equals(e.className, "", "removing the last token empties className");
}, "removing the last token");

test(function () {
  var e = el();
  assert_throws_dom("SyntaxError", function () { e.classList.add(""); },
    "the empty string is not a valid token");
}, "add('') throws");

test(function () {
  var e = el();
  assert_throws_dom("InvalidCharacterError", function () { e.classList.add("a b"); },
    "a token may not contain whitespace");
}, "add() with an embedded space throws");
