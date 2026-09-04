// Functions: closures, default / rest params, arrow `this`, arguments,
// recursion, IIFE, generators (best effort).

test262("closures capture by reference", function () {
  function counter() { var n = 0; return function () { return ++n; }; }
  var c = counter();
  assert.sameValue(c(), 1);
  assert.sameValue(c(), 2);
  assert.sameValue(counter()(), 1);
});

test262("default parameters", function () {
  function greet(name = "world", punct = "!") { return "hi " + name + punct; }
  assert.sameValue(greet(), "hi world!");
  assert.sameValue(greet("bob"), "hi bob!");
  assert.sameValue(greet("bob", "."), "hi bob.");
  assert.sameValue(greet(undefined, "?"), "hi world?");
});

test262("default parameter can reference earlier params", function () {
  function f(a, b = a * 2) { return a + b; }
  assert.sameValue(f(3), 9);
  assert.sameValue(f(3, 1), 4);
});

test262("rest parameters", function () {
  function f(first, ...rest) { return first + ":" + rest.join(","); }
  assert.sameValue(f(1, 2, 3, 4), "1:2,3,4");
  assert.sameValue(f(1), "1:");
});

test262("arguments object", function () {
  function f() { return arguments.length + ":" + arguments[0]; }
  assert.sameValue(f("a", "b", "c"), "3:a");
});

test262("arrow functions have no own arguments and lexical this", function () {
  var obj = {
    val: 10,
    make: function () { return () => this.val; }
  };
  assert.sameValue(obj.make()(), 10);
});

test262("arrow function implicit return", function () {
  var sq = x => x * x;
  assert.sameValue(sq(5), 25);
  var pair = (a, b) => ({ a: a, b: b });
  assert.sameValue(pair(1, 2).b, 2);
});

test262("recursion", function () {
  function fib(n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }
  assert.sameValue(fib(10), 55);
});

test262("IIFE", function () {
  var r = (function (x) { return x + 1; })(41);
  assert.sameValue(r, 42);
});

test262("function.length and function.name", function () {
  function f(a, b, c) {}
  assert.sameValue(f.length, 3);
  assert.sameValue(f.name, "f");
  var g = function named() {};
  assert.sameValue(g.name, "named");
});

test262("call and apply", function () {
  function greet(greeting) { return greeting + " " + this.name; }
  var ctx = { name: "Ada" };
  assert.sameValue(greet.call(ctx, "hi"), "hi Ada");
  assert.sameValue(greet.apply(ctx, ["hey"]), "hey Ada");
});

test262("bind", function () {
  function add(a, b) { return a + b + this.base; }
  var bound = add.bind({ base: 100 }, 1);
  assert.sameValue(bound(2), 103);
});

test262("higher-order composition", function () {
  var compose = (f, g) => x => f(g(x));
  var addOne = x => x + 1;
  var double = x => x * 2;
  assert.sameValue(compose(addOne, double)(5), 11);
});

test262("generator function basics", function () {
  function* gen() { yield 1; yield 2; yield 3; }
  var out = [];
  for (var v of gen()) out.push(v);
  assert.compareArray(out, [1, 2, 3]);
});

test262("generator with return value via next()", function () {
  function* g() { var x = yield 1; yield x + 1; }
  var it = g();
  assert.sameValue(it.next().value, 1);
  assert.sameValue(it.next(10).value, 11);
});
