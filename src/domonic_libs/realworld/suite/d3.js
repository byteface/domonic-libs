test(function () {
  assert_equals(d3.max([1, 5, 3]), 5, "d3.max finds the largest value");
}, "d3.max");

test(function () {
  assert_array_equals(d3.range(0, 5), [0, 1, 2, 3, 4], "d3.range generates a sequence");
}, "d3.range");

test(function () {
  var scale = d3.scaleLinear().domain([0, 10]).range([0, 100]);
  assert_equals(scale(5), 50, "linear scale interpolates the midpoint");
}, "d3.scaleLinear");
