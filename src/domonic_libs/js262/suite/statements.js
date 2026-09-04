// Language statements: for / for-of / for-in, while, do-while, switch,
// try/catch/finally, labelled break, block scoping.

test262("for loop with continue and break", function () {
  var s = 0;
  for (var i = 0; i < 10; i++) { if (i % 2) continue; if (i > 6) break; s += i; }
  assert.sameValue(s, 12);   // 0 + 2 + 4 + 6
});

test262("for-of over an array", function () {
  var out = [];
  for (var x of [10, 20, 30]) out.push(x);
  assert.compareArray(out, [10, 20, 30]);
});

test262("for-of over a string yields code points", function () {
  var out = [];
  for (var ch of "abc") out.push(ch);
  assert.compareArray(out, ["a", "b", "c"]);
});

test262("for-of with destructuring", function () {
  var pairs = [[1, "a"], [2, "b"]];
  var keys = [];
  for (var [n, s] of pairs) keys.push(n + s);
  assert.compareArray(keys, ["1a", "2b"]);
});

test262("for-in over object keys", function () {
  var o = { a: 1, b: 2, c: 3 };
  var keys = [];
  for (var k in o) keys.push(k);
  keys.sort();
  assert.compareArray(keys, ["a", "b", "c"]);
});

test262("while and do-while", function () {
  var n = 0;
  while (n < 5) n++;
  assert.sameValue(n, 5);
  var m = 10;
  do { m--; } while (m > 8);
  assert.sameValue(m, 8);
});

test262("switch with fallthrough and default", function () {
  function classify(n) {
    var out = "";
    switch (n) {
      case 1:
      case 2:
        out = "low"; break;
      case 3:
        out = "mid";
      case 4:
        out += "!"; break;
      default:
        out = "other";
    }
    return out;
  }
  assert.sameValue(classify(1), "low");
  assert.sameValue(classify(2), "low");
  assert.sameValue(classify(3), "mid!");
  assert.sameValue(classify(4), "!");
  assert.sameValue(classify(9), "other");
});

test262("try / catch / finally ordering", function () {
  var log = [];
  function f() {
    try { log.push("try"); throw new Error("x"); }
    catch (e) { log.push("catch"); return "caught"; }
    finally { log.push("finally"); }
  }
  assert.sameValue(f(), "caught");
  assert.compareArray(log, ["try", "catch", "finally"]);
});

test262("finally runs even on return from try", function () {
  var ran = false;
  function f() { try { return 1; } finally { ran = true; } }
  assert.sameValue(f(), 1);
  assert.sameValue(ran, true);
});

test262("optional catch binding", function () {
  var caught = false;
  try { throw new Error("x"); } catch { caught = true; }
  assert.sameValue(caught, true);
});

test262("re-throw from catch", function () {
  assert.throws(TypeError, function () {
    try { throw new TypeError("boom"); } catch (e) { throw e; }
  });
});

test262("labelled break from nested loops", function () {
  var hits = 0;
  outer: for (var i = 0; i < 3; i++) {
    for (var j = 0; j < 3; j++) {
      if (i === 1 && j === 1) break outer;
      hits++;
    }
  }
  assert.sameValue(hits, 4);
});

test262("block scoping of let / const", function () {
  var x = 1;
  { let x = 2; assert.sameValue(x, 2); }
  assert.sameValue(x, 1);
});

test262("let in a loop closes over per-iteration binding", function () {
  var fns = [];
  for (let i = 0; i < 3; i++) fns.push(function () { return i; });
  assert.compareArray([fns[0](), fns[1](), fns[2]()], [0, 1, 2]);
});

test262("const cannot be reassigned", function () {
  assert.throws(TypeError, function () {
    eval("const c = 1; c = 2;");
  });
});

test262("hoisted function declarations", function () {
  assert.sameValue(hoisted(), 42);
  function hoisted() { return 42; }
});
