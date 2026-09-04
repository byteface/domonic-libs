// Element.dataset (DOMStringMap). WPT: dom/nodes/Element-dataset*.html.
// https://html.spec.whatwg.org/#dom-dataset

function el() { return document.createElement("div"); }

test(function () {
  var e = el();
  e.setAttribute("data-foo", "1");
  assert_equals(e.dataset.foo, "1", "a data-* attribute is readable via dataset");
}, "dataset reads a data-* attribute");

test(function () {
  var e = el();
  e.setAttribute("data-foo-bar", "2");
  assert_equals(e.dataset.fooBar, "2", "hyphen-lower maps to camelCase");
}, "dataset name -> camelCase mapping");

test(function () {
  var e = el();
  e.dataset.baz = "3";
  assert_equals(e.getAttribute("data-baz"), "3", "dataset writes reflect into the attribute");
  assert_equals(e.dataset.baz, "3");
}, "writing dataset sets a data-* attribute");

test(function () {
  var e = el();
  e.dataset.camelCase = "4";
  assert_equals(e.getAttribute("data-camel-case"), "4", "camelCase -> hyphen-lower on write");
}, "dataset camelCase -> attribute name mapping");

test(function () {
  var e = el();
  e.dataset.foo = "1";
  delete e.dataset.foo;
  assert_false(e.hasAttribute("data-foo"), "delete removes the attribute");
  assert_equals(e.dataset.foo, undefined, "a missing dataset entry is undefined");
}, "deleting a dataset entry");

test(function () {
  var e = el();
  e.dataset.foo = "1";
  assert_true("foo" in e.dataset, "the in operator sees dataset entries");
  assert_false("bar" in e.dataset);
}, "the in operator over dataset");

test(function () {
  var e = el();
  e.dataset.a = "1";
  e.dataset.b = "2";
  var keys = [];
  for (var k in e.dataset) keys.push(k);
  keys.sort();
  assert_array_equals(keys, ["a", "b"], "for-in enumerates dataset keys");
}, "for-in over dataset");
