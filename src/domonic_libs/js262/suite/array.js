// Array.prototype and Array statics. Mirrors test262 built-ins/Array/prototype/*.

test262("Array.isArray", function () {
  assert.sameValue(Array.isArray([]), true);
  assert.sameValue(Array.isArray([1, 2]), true);
  assert.sameValue(Array.isArray("no"), false);
  assert.sameValue(Array.isArray({ length: 0 }), false);
});

test262("Array.from", function () {
  assert.compareArray(Array.from("abc"), ["a", "b", "c"]);
  assert.compareArray(Array.from([1, 2, 3], x => x * 2), [2, 4, 6]);
  assert.compareArray(Array.from({ length: 3 }, (_, i) => i), [0, 1, 2]);
});

test262("Array.of", function () {
  assert.compareArray(Array.of(1, 2, 3), [1, 2, 3]);
  assert.compareArray(Array.of(7), [7]);
});

test262("map / filter / reduce", function () {
  assert.compareArray([1, 2, 3].map(x => x * x), [1, 4, 9]);
  assert.compareArray([1, 2, 3, 4].filter(x => x % 2 === 0), [2, 4]);
  assert.sameValue([1, 2, 3, 4].reduce((a, b) => a + b), 10);
  assert.sameValue([1, 2, 3].reduce((a, b) => a + b, 100), 106);
  assert.sameValue([].reduce((a, b) => a + b, 0), 0);
});

test262("reduceRight", function () {
  assert.sameValue(["a", "b", "c"].reduceRight((a, b) => a + b), "cba");
});

test262("forEach", function () {
  var sum = 0;
  [1, 2, 3].forEach(function (x) { sum += x; });
  assert.sameValue(sum, 6);
});

test262("find / findIndex / findLast", function () {
  assert.sameValue([1, 2, 3, 4].find(x => x > 2), 3);
  assert.sameValue([1, 2, 3, 4].findIndex(x => x > 2), 2);
  assert.sameValue([1, 2, 3, 4].find(x => x > 9), undefined);
  assert.sameValue([1, 2, 3, 4].findLast(x => x % 2 === 1), 3);
});

test262("some / every", function () {
  assert.sameValue([1, 2, 3].some(x => x > 2), true);
  assert.sameValue([1, 2, 3].every(x => x > 0), true);
  assert.sameValue([1, 2, 3].every(x => x > 1), false);
});

test262("includes / indexOf / lastIndexOf", function () {
  assert.sameValue([1, 2, 3].includes(2), true);
  assert.sameValue([1, 2, 3].includes(9), false);
  assert.sameValue([1, 2, 3, 2].indexOf(2), 1);
  assert.sameValue([1, 2, 3, 2].lastIndexOf(2), 3);
  assert.sameValue([1, 2, 3].indexOf(9), -1);
});

test262("slice and splice", function () {
  assert.compareArray([1, 2, 3, 4, 5].slice(1, 3), [2, 3]);
  assert.compareArray([1, 2, 3, 4, 5].slice(-2), [4, 5]);
  var a = [1, 2, 3, 4, 5];
  var removed = a.splice(1, 2, "x");
  assert.compareArray(removed, [2, 3]);
  assert.compareArray(a, [1, "x", 4, 5]);
});

test262("push / pop / shift / unshift", function () {
  var a = [2, 3];
  assert.sameValue(a.push(4), 3);
  assert.sameValue(a.unshift(1), 4);
  assert.compareArray(a, [1, 2, 3, 4]);
  assert.sameValue(a.pop(), 4);
  assert.sameValue(a.shift(), 1);
  assert.compareArray(a, [2, 3]);
});

test262("concat / join / reverse", function () {
  assert.compareArray([1, 2].concat([3, 4], 5), [1, 2, 3, 4, 5]);
  assert.sameValue([1, 2, 3].join("-"), "1-2-3");
  assert.sameValue([1, 2, 3].join(), "1,2,3");
  assert.compareArray([1, 2, 3].reverse(), [3, 2, 1]);
});

test262("sort with and without comparator", function () {
  assert.compareArray([3, 1, 2].sort(), [1, 2, 3]);
  assert.compareArray([10, 1, 2].sort(), [1, 10, 2]);   // default is string sort
  assert.compareArray([10, 1, 2].sort((a, b) => a - b), [1, 2, 10]);
});

test262("flat and flatMap", function () {
  assert.compareArray([1, [2, 3], [4]].flat(), [1, 2, 3, 4]);
  assert.compareArray([1, [2, [3, [4]]]].flat(3), [1, 2, 3, 4]);
  assert.sameValue([1, [2, [3]]].flat().length, 3);   // depth 1: [1, 2, [3]]
  assert.compareArray([1, 2, 3].flatMap(x => [x, x * 10]), [1, 10, 2, 20, 3, 30]);
});

test262("at", function () {
  assert.sameValue([1, 2, 3].at(0), 1);
  assert.sameValue([1, 2, 3].at(-1), 3);
  assert.sameValue([1, 2, 3].at(9), undefined);
});

test262("fill and copyWithin", function () {
  assert.compareArray([1, 2, 3, 4].fill(0, 1, 3), [1, 0, 0, 4]);
});

test262("keys / values / entries", function () {
  assert.compareArray([...["a", "b"].keys()], [0, 1]);
  assert.compareArray([...["a", "b"].values()], ["a", "b"]);
  var e = [...["a", "b"].entries()];
  assert.compareArray(e[0], [0, "a"]);
  assert.compareArray(e[1], [1, "b"]);
});

test262("length is writable", function () {
  var a = [1, 2, 3, 4, 5];
  a.length = 2;
  assert.compareArray(a, [1, 2]);
});

test262("spread and destructuring interplay", function () {
  var [head, ...tail] = [1, 2, 3, 4];
  assert.sameValue(head, 1);
  assert.compareArray([...tail, ...tail], [2, 3, 4, 2, 3, 4]);
});

test262("toSorted / toReversed (immutable)", function () {
  var a = [3, 1, 2];
  var b = a.toSorted((x, y) => x - y);
  assert.compareArray(a, [3, 1, 2]);
  assert.compareArray(b, [1, 2, 3]);
});
