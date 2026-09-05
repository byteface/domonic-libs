test(function () {
  assert_array_equals(_.chunk([1, 2, 3, 4], 2)[0], [1, 2], "chunk first pair");
}, "_.chunk splits into pairs");

test(function () {
  assert_array_equals(_.uniq([1, 2, 2, 3, 1]), [1, 2, 3], "uniq dedupes preserving order");
}, "_.uniq");

test(function () {
  assert_equals(_.get({ a: { b: 42 } }, "a.b"), 42, "get resolves a dotted path");
}, "_.get");

test(function () {
  var doubled = _.map([1, 2, 3], function (x) { return x * 2; });
  assert_array_equals(doubled, [2, 4, 6], "map doubles each element");
}, "_.map");
