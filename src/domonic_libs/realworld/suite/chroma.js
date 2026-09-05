test(function () {
  assert_equals(chroma("red").hex(), "#ff0000", "named color to hex");
}, "chroma hex conversion");

test(function () {
  var rgb = chroma(255, 0, 0).rgb();
  assert_array_equals(rgb, [255, 0, 0], "rgb() round-trip");
}, "chroma rgb");

test(function () {
  var mixed = chroma.mix("#ff0000", "#0000ff", 0.5).hex();
  assert_true(typeof mixed === "string" && mixed.charAt(0) === "#", "mix produces a hex color");
}, "chroma.mix");
