// Element attribute reflection. WPT: dom/nodes/attributes.html and
// dom/nodes/Element-{get,set,remove,has}Attribute*.html.

function el(tag) { return document.createElement(tag || "div"); }

test(function () {
  var e = el();
  e.setAttribute("id", "x");
  assert_equals(e.getAttribute("id"), "x");
  assert_true(e.hasAttribute("id"));
}, "setAttribute / getAttribute / hasAttribute");

test(function () {
  var e = el();
  e.setAttribute("id", "x");
  e.setAttribute("id", "y");
  assert_equals(e.getAttribute("id"), "y", "a second setAttribute overwrites");
}, "setAttribute overwrites");

test(function () {
  var e = el();
  e.setAttribute("id", "x");
  e.removeAttribute("id");
  assert_false(e.hasAttribute("id"));
  assert_equals(e.getAttribute("id"), null, "a removed attribute reads back as null");
}, "removeAttribute");

test(function () {
  var e = el();
  assert_equals(e.getAttribute("nope"), null, "an absent attribute is null, not empty string");
}, "getAttribute of an absent attribute");

test(function () {
  var e = el();
  e.id = "y";
  assert_equals(e.getAttribute("id"), "y", "the id IDL attribute reflects into the content attribute");
}, "id IDL attribute reflection");

test(function () {
  var e = el();
  e.setAttribute("class", "a b");
  assert_equals(e.className, "a b", "className reflects the class attribute");
  assert_equals(e.classList.length, 2);
}, "class attribute <-> className / classList");

test(function () {
  var e = el();
  assert_true(e.toggleAttribute("hidden"), "toggleAttribute adds and returns true");
  assert_true(e.hasAttribute("hidden"));
  assert_false(e.toggleAttribute("hidden"), "toggleAttribute removes and returns false");
  assert_false(e.hasAttribute("hidden"));
}, "toggleAttribute");

test(function () {
  var e = el();
  e.setAttribute("data-x", "1");
  assert_equals(e.getAttribute("data-x"), "1", "data-* is a plain attribute too");
}, "data-* attribute via getAttribute");

test(function () {
  var e = el();
  e.setAttribute("title", "T");
  assert_true(typeof e.getAttributeNames === "function", "getAttributeNames is present");
  assert_array_equals(e.getAttributeNames(), ["title"]);
}, "getAttributeNames");

test(function () {
  var e = el();
  e.setAttribute("FOO", "1");
  assert_equals(e.getAttribute("foo"), "1",
    "attribute names on HTML elements are ASCII-lowercased");
}, "attribute names are case-insensitive on HTML elements");
