test(function () {
  var template = Handlebars.compile("Hello {{name}}!");
  assert_equals(template({ name: "World" }), "Hello World!", "basic interpolation");
}, "Handlebars.compile interpolation");

test(function () {
  var template = Handlebars.compile("{{#each items}}({{this}}){{/each}}");
  assert_equals(template({ items: [1, 2, 3] }), "(1)(2)(3)", "#each loop over an array");
}, "Handlebars #each helper");
