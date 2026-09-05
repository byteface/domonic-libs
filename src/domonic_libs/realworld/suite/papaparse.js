test(function () {
  var result = Papa.parse("a,b,c\n1,2,3");
  assert_array_equals(result.data[0], ["a", "b", "c"], "header row");
  assert_array_equals(result.data[1], ["1", "2", "3"], "data row");
}, "Papa.parse basic CSV");

test(function () {
  var result = Papa.parse("name,age\nAda,36", { header: true });
  assert_equals(result.data[0].name, "Ada", "header:true maps column names");
  assert_equals(result.data[0].age, "36", "header:true keeps other columns");
}, "Papa.parse with header option");
