// Promises, async / await, the event loop. Mirrors built-ins/Promise/* and
// language/expressions/await. The interpreter runs the loop to quiescence at
// the end of the file, so a check that appends to a shared array and asserts
// its contents at the end works.

test262("Promise.resolve and .then", function () {
  var seen;
  Promise.resolve(42).then(function (v) { seen = v; });
  // drained before the file ends; re-check via a second microtask
  Promise.resolve().then(function () { assert.sameValue(seen, 42); });
});

test262("Promise constructor executor", function () {
  var out;
  new Promise(function (resolve) { resolve("done"); }).then(function (v) { out = v; });
  Promise.resolve().then(function () { assert.sameValue(out, "done"); });
});

test262("Promise rejection and .catch", function () {
  var err;
  Promise.reject(new Error("nope")).catch(function (e) { err = e.message; });
  Promise.resolve().then(function () {
    Promise.resolve().then(function () { assert.sameValue(err, "nope"); });
  });
});

test262("then chaining transforms the value", function () {
  var result;
  Promise.resolve(2)
    .then(function (v) { return v * 10; })
    .then(function (v) { return v + 1; })
    .then(function (v) { result = v; });
  Promise.resolve().then(function () {
    Promise.resolve().then(function () {
      Promise.resolve().then(function () { assert.sameValue(result, 21); });
    });
  });
});

test262("Promise.all", function () {
  var got;
  Promise.all([1, Promise.resolve(2), 3]).then(function (vs) { got = vs; });
  Promise.resolve().then(function () {
    Promise.resolve().then(function () { assert.compareArray(got, [1, 2, 3]); });
  });
});

test262("Promise.race", function () {
  var winner;
  Promise.race([Promise.resolve("fast"), new Promise(function () {})]).then(function (v) { winner = v; });
  Promise.resolve().then(function () {
    Promise.resolve().then(function () { assert.sameValue(winner, "fast"); });
  });
});

test262("Promise.allSettled", function () {
  var out;
  Promise.allSettled([Promise.resolve(1), Promise.reject("e")]).then(function (rs) { out = rs; });
  Promise.resolve().then(function () {
    Promise.resolve().then(function () {
      assert.sameValue(out[0].status, "fulfilled");
      assert.sameValue(out[0].value, 1);
      assert.sameValue(out[1].status, "rejected");
      assert.sameValue(out[1].reason, "e");
    });
  });
});

test262("async function returns a promise", function () {
  async function f() { return 5; }
  var r = f();
  assert.sameValue(typeof r.then, "function");
  r.then(function (v) { assert.sameValue(v, 5); });
});

test262("await unwraps a promise", function () {
  var out;
  (async function () {
    var a = await Promise.resolve(20);
    var b = await Promise.resolve(22);
    out = a + b;
  })();
  Promise.resolve().then(function () { assert.sameValue(out, 42); });
});

test262("await in a try / catch handles rejection", function () {
  var caught;
  (async function () {
    try { await Promise.reject(new TypeError("bad")); }
    catch (e) { caught = e.name; }
  })();
  Promise.resolve().then(function () {
    Promise.resolve().then(function () { assert.sameValue(caught, "TypeError"); });
  });
});

test262("await on a non-promise passes through", function () {
  var out;
  (async function () { out = await 7; })();
  Promise.resolve().then(function () { assert.sameValue(out, 7); });
});

test262("microtasks run before timers", function () {
  var order = [];
  setTimeout(function () { order.push("timeout"); }, 0);
  Promise.resolve().then(function () { order.push("micro"); });
  order.push("sync");
  setTimeout(function () {
    assert.compareArray(order, ["sync", "micro", "timeout"]);
  }, 5);
});

test262("setTimeout / clearTimeout", function () {
  var fired = false;
  var id = setTimeout(function () { fired = true; }, 5);
  clearTimeout(id);
  setTimeout(function () { assert.sameValue(fired, false); }, 15);
});
