test(function () {
  assert_array_equals(R.map(function (x) { return x * 2; }, [1, 2, 3]), [2, 4, 6], "map doubles");
}, "R.map");

test(function () {
  var add5 = R.add(5);
  assert_equals(add5(10), 15, "curried add(5)(10)");
}, "R.add currying");

test(function () {
  var pipeline = R.pipe(R.map(R.multiply(2)), R.filter(function (x) { return x > 4; }));
  assert_array_equals(pipeline([1, 2, 3, 4]), [6, 8], "pipe composes map + filter");
}, "R.pipe composition");
