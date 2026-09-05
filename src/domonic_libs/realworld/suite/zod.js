test(function () {
  assert_equals(Zod.z.string().parse("hi"), "hi", "string schema accepts a string");
}, "Zod string schema");

test(function () {
  assert_throws_js("Error", function () { Zod.z.string().parse(42); }, "string schema rejects a number");
}, "Zod schema validation failure");

test(function () {
  var schema = Zod.z.object({ name: Zod.z.string(), age: Zod.z.number() });
  var parsed = schema.parse({ name: "Ada", age: 36 });
  assert_equals(parsed.name, "Ada", "object schema parses name");
  assert_equals(parsed.age, 36, "object schema parses age");
}, "Zod object schema");
