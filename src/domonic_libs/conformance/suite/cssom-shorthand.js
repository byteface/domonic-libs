// Shorthand <-> longhand expansion. WPT: css/cssom/shorthand-serialization.html
// and css/cssom/serialize-values.html. domonic currently stores shorthands
// verbatim without expanding them, so most of these are expected gaps.

function el() { return document.createElement("div"); }

test(function () {
  var s = el().style;
  s.margin = "1px 2px 3px 4px";
  assert_equals(s.marginTop, "1px", "margin shorthand sets margin-top");
  assert_equals(s.marginRight, "2px", "margin shorthand sets margin-right");
  assert_equals(s.marginBottom, "3px", "margin shorthand sets margin-bottom");
  assert_equals(s.marginLeft, "4px", "margin shorthand sets margin-left");
}, "margin shorthand expands to four longhands");

test(function () {
  var s = el().style;
  s.margin = "1px 2px 3px 4px";
  assert_equals(s.length, 4, "shorthand is stored as its longhands");
}, "shorthand contributes its longhands to length");

test(function () {
  var s = el().style;
  s.marginTop = "1px";
  s.marginRight = "1px";
  s.marginBottom = "1px";
  s.marginLeft = "1px";
  assert_equals(s.margin, "1px", "four equal longhands serialise back to the shorthand");
}, "longhands collapse into the margin shorthand");

test(function () {
  var s = el().style;
  s.padding = "0";
  assert_equals(s.paddingTop, "0px", "padding: 0 normalises to 0px longhands");
}, "padding shorthand with a bare zero");
