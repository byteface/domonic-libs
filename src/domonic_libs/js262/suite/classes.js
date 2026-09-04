// Classes: constructor, methods, extends / super, static members, fields,
// getters / setters, instanceof, private fields (best effort).

test262("basic class with constructor and method", function () {
  class Point {
    constructor(x, y) { this.x = x; this.y = y; }
    dist() { return Math.sqrt(this.x * this.x + this.y * this.y); }
  }
  var p = new Point(3, 4);
  assert.sameValue(p.x, 3);
  assert.sameValue(p.dist(), 5);
  assert.sameValue(p instanceof Point, true);
});

test262("extends and super", function () {
  class Animal {
    constructor(name) { this.name = name; }
    speak() { return this.name + " makes a sound"; }
  }
  class Dog extends Animal {
    constructor(name) { super(name); this.legs = 4; }
    speak() { return super.speak() + " (woof)"; }
  }
  var d = new Dog("Rex");
  assert.sameValue(d.name, "Rex");
  assert.sameValue(d.legs, 4);
  assert.sameValue(d.speak(), "Rex makes a sound (woof)");
  assert.sameValue(d instanceof Dog, true);
  assert.sameValue(d instanceof Animal, true);
});

test262("static members", function () {
  class MathUtil {
    static square(x) { return x * x; }
    static PI = 3.14;
  }
  assert.sameValue(MathUtil.square(4), 16);
  assert.sameValue(MathUtil.PI, 3.14);
});

test262("instance fields", function () {
  class Box {
    value = 0;
    label = "empty";
  }
  var b = new Box();
  assert.sameValue(b.value, 0);
  assert.sameValue(b.label, "empty");
});

test262("getters and setters", function () {
  class Temp {
    constructor(c) { this._c = c; }
    get fahrenheit() { return this._c * 9 / 5 + 32; }
    set fahrenheit(f) { this._c = (f - 32) * 5 / 9; }
  }
  var t = new Temp(0);
  assert.sameValue(t.fahrenheit, 32);
  t.fahrenheit = 212;
  assert.sameValue(t._c, 100);
});

test262("computed method names", function () {
  var key = "dynamic";
  class C { [key]() { return "ok"; } }
  assert.sameValue(new C().dynamic(), "ok");
});

test262("class expression", function () {
  var C = class { hello() { return "hi"; } };
  assert.sameValue(new C().hello(), "hi");
});

test262("methods are not enumerable on the instance", function () {
  class C { m() {} }
  var keys = [];
  for (var k in new C()) keys.push(k);
  assert.sameValue(keys.length, 0);
});

test262("private fields", function () {
  class Counter {
    #count = 0;
    inc() { this.#count++; return this.#count; }
  }
  var c = new Counter();
  assert.sameValue(c.inc(), 1);
  assert.sameValue(c.inc(), 2);
});

test262("super in a static method", function () {
  class A { static who() { return "A"; } }
  class B extends A { static who() { return super.who() + "B"; } }
  assert.sameValue(B.who(), "AB");
});

test262("chained inheritance", function () {
  class A { m() { return "a"; } }
  class B extends A { m() { return super.m() + "b"; } }
  class C extends B { m() { return super.m() + "c"; } }
  assert.sameValue(new C().m(), "abc");
});

test262("toString override", function () {
  class Money {
    constructor(n) { this.n = n; }
    toString() { return "$" + this.n; }
  }
  assert.sameValue("" + new Money(5), "$5");
  assert.sameValue(`${new Money(9)}`, "$9");
});
