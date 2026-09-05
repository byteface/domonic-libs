test(function () {
  var html = katex.renderToString("x^2 + y^2 = z^2");
  assert_true(typeof html === "string" && html.indexOf("katex") !== -1, "renders real KaTeX markup");
}, "katex.renderToString basic");

test(function () {
  assert_throws_js("Error", function () { katex.renderToString("\\notarealcommand"); }, "an unknown macro throws");
}, "katex.renderToString invalid input");
