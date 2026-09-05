test(function () {
  assert_equals(Mustache.render("Hello {{name}}!", { name: "World" }), "Hello World!", "basic interpolation");
}, "Mustache.render interpolation");

test(function () {
  var out = Mustache.render("{{#items}}({{.}}){{/items}}", { items: [1, 2, 3] });
  assert_equals(out, "(1)(2)(3)", "section loop over an array");
}, "Mustache.render section loop");
