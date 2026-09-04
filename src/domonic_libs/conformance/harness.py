"""A small ``testharness.js``-compatible shim, in JavaScript.

The string below is prepended to every conformance ``.js`` file before it is
handed to the tree-walking interpreter.  It provides the subset of Web Platform
Tests' ``testharness.js`` that the curated CSSOM / DOM suite in ``suite/`` uses:
``test`` / ``promise_test`` and the ``assert_*`` family.

Two deliberate simplifications versus the real harness:

* ``promise_test`` runs its body synchronously -- there is no event loop yet, so
  a returned promise is only awaited if the interpreter can resolve it eagerly.
* ``assert_throws_dom`` matches on the thrown value's ``name`` rather than the
  full ``DOMException`` interface.

Results accumulate on the global ``__results`` array as
``{name, status: "PASS"|"FAIL", message}`` -- the runner reads that back.
"""

HARNESS_JS = r"""
var __results = [];

function __fmt(v) {
  if (typeof v === "string") return JSON.stringify(v);
  if (v === null) return "null";
  if (v === undefined) return "undefined";
  return String(v);
}

function __record(name, body) {
  try {
    body();
    __results.push({ name: name, status: "PASS", message: "" });
  } catch (e) {
    var msg = (e && e.message) ? e.message : String(e);
    __results.push({ name: name, status: "FAIL", message: msg });
  }
}

function test(fn, name) { __record(name || "(anonymous)", fn); }
function promise_test(fn, name) { __record(name || "(anonymous)", function () { fn(); }); }
function setup() {}
function done() {}

function assert_true(actual, description) {
  if (actual !== true)
    throw new Error((description || "assert_true") + ": expected true got " + __fmt(actual));
}
function assert_false(actual, description) {
  if (actual !== false)
    throw new Error((description || "assert_false") + ": expected false got " + __fmt(actual));
}
function assert_equals(actual, expected, description) {
  if (actual !== expected)
    throw new Error((description || "assert_equals") + ": expected " + __fmt(expected) + " got " + __fmt(actual));
}
function assert_not_equals(actual, expected, description) {
  if (actual === expected)
    throw new Error((description || "assert_not_equals") + ": got disallowed value " + __fmt(actual));
}
function assert_in_array(actual, expected, description) {
  for (var i = 0; i < expected.length; i++) if (expected[i] === actual) return;
  throw new Error((description || "assert_in_array") + ": " + __fmt(actual) + " not in " + __fmt(expected));
}
function assert_array_equals(actual, expected, description) {
  var d = description || "assert_array_equals";
  if (actual.length !== expected.length)
    throw new Error(d + ": length " + actual.length + " !== " + expected.length);
  for (var i = 0; i < expected.length; i++)
    if (actual[i] !== expected[i])
      throw new Error(d + ": index " + i + " expected " + __fmt(expected[i]) + " got " + __fmt(actual[i]));
}
function assert_own_property(obj, name, description) {
  if (!(name in obj))
    throw new Error((description || "assert_own_property") + ": missing property " + __fmt(name));
}
function assert_class_string(obj, s, description) {
  assert_equals(Object.prototype.toString.call(obj), "[object " + s + "]", description);
}

function __expected_name(expected) {
  if (typeof expected === "string") return expected;
  if (expected && expected.name) return expected.name;
  return null;
}
function assert_throws_js(expected, fn, description) {
  var d = description || "assert_throws_js";
  var want = __expected_name(expected);
  try { fn(); } catch (e) {
    if (want && e && e.name && e.name !== want)
      throw new Error(d + ": threw " + e.name + " expected " + want);
    return;
  }
  throw new Error(d + ": did not throw");
}
function assert_throws_dom(name, fn, description) {
  var d = description || "assert_throws_dom";
  try { fn(); } catch (e) { return; }
  throw new Error(d + ": did not throw");
}
"""
