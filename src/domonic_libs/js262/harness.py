"""A test262-compatible harness, in JavaScript.

The string below is prepended to every ``.js`` file in ``suite/`` before it is
handed to ``domonic_libs.acorn.interpret``. It provides the parts of test262's
``harness/`` that the curated battery uses: ``Test262Error``, the ``assert``
object (``assert``, ``assert.sameValue``, ``assert.notSameValue``,
``assert.throws``, ``assert.compareArray``), and ``verifyProperty``-lite.

On top of test262 it adds ``test262(name, fn)`` -- a batching wrapper so one
file can hold many independent checks and the runner can score pass/fail per
check instead of aborting the file on the first failure. Results accumulate on
the global ``$RESULTS``.
"""

HARNESS_JS = r"""
var $RESULTS = [];

function Test262Error(message) { this.message = message || ""; this.name = "Test262Error"; }
Test262Error.prototype.toString = function () { return "Test262Error: " + this.message; };
Test262Error.thrower = function (message) { throw new Test262Error(message); };

function $DONOTEVALUATE() { throw new Test262Error("This code should not be evaluated."); }

function $fmt(v) {
  if (typeof v === "string") return JSON.stringify(v);
  if (v === null) return "null";
  if (v === undefined) return "undefined";
  if (typeof v === "number" && v !== v) return "NaN";
  return String(v);
}

function assert(mustBeTrue, message) {
  if (mustBeTrue === true) return;
  throw new Test262Error((message || "assert") + " (got " + $fmt(mustBeTrue) + ")");
}

assert._isSameValue = function (a, b) {
  if (a === b) return a !== 0 || 1 / a === 1 / b;   // distinguish +0 / -0
  return a !== a && b !== b;                         // NaN
};

assert.sameValue = function (actual, expected, message) {
  if (assert._isSameValue(actual, expected)) return;
  throw new Test262Error((message || "sameValue") + ": expected " + $fmt(expected) + " got " + $fmt(actual));
};

assert.notSameValue = function (actual, unexpected, message) {
  if (!assert._isSameValue(actual, unexpected)) return;
  throw new Test262Error((message || "notSameValue") + ": got disallowed value " + $fmt(actual));
};

assert.throws = function (expectedErrorConstructor, func, message) {
  var m = message || "assert.throws";
  var want = (typeof expectedErrorConstructor === "function" && expectedErrorConstructor.name)
    || expectedErrorConstructor;
  try {
    func();
  } catch (thrown) {
    var got = (thrown && thrown.name) || String(thrown);
    if (want && got !== want) {
      throw new Test262Error(m + ": threw " + got + ", wanted " + want);
    }
    return;
  }
  throw new Test262Error(m + ": no exception thrown, wanted " + want);
};

assert.compareArray = function (actual, expected, message) {
  var m = message || "compareArray";
  if (actual.length !== expected.length) {
    throw new Test262Error(m + ": length " + actual.length + " !== " + expected.length);
  }
  for (var i = 0; i < expected.length; i++) {
    if (!assert._isSameValue(actual[i], expected[i])) {
      throw new Test262Error(m + ": index " + i + " expected " + $fmt(expected[i]) + " got " + $fmt(actual[i]));
    }
  }
};

function compareArray(a, b) {
  if (a.length !== b.length) return false;
  for (var i = 0; i < a.length; i++) if (!assert._isSameValue(a[i], b[i])) return false;
  return true;
}

function verifyProperty(obj, name, desc) {
  if (!(name in obj)) throw new Test262Error("verifyProperty: missing " + name);
  if (desc && "value" in desc) assert.sameValue(obj[name], desc.value, "verifyProperty value of " + name);
}

// -- batching wrapper (not part of test262) --------------------------------
function test262(name, fn) {
  try {
    fn();
    $RESULTS.push({ name: name, status: "PASS", message: "" });
  } catch (e) {
    var msg = (e && e.message !== undefined) ? e.message : String(e);
    $RESULTS.push({ name: name, status: "FAIL", message: msg });
  }
}
"""
