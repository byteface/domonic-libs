// CSSStyleDeclaration basics -- modelled on WPT css/cssom/*.
// https://drafts.csswg.org/cssom/#the-cssstyledeclaration-interface

function el() { return document.createElement("div"); }

test(function () {
  var s = el().style;
  s.color = "red";
  assert_equals(s.color, "red", "camelCase getter round-trips");
}, "setting a property via a camelCase IDL attribute");

test(function () {
  var s = el().style;
  s.setProperty("color", "red");
  assert_equals(s.getPropertyValue("color"), "red");
  assert_equals(s.color, "red", "setProperty is visible via the IDL attribute");
}, "setProperty then getPropertyValue / IDL attribute");

test(function () {
  var s = el().style;
  s.setProperty("background-color", "blue");
  assert_equals(s.backgroundColor, "blue", "kebab property visible as camelCase");
}, "kebab-case setProperty maps to the camelCase attribute");

test(function () {
  var s = el().style;
  s.setProperty("color", "green", "important");
  assert_equals(s.getPropertyPriority("color"), "important");
}, "getPropertyPriority reports !important");

test(function () {
  var s = el().style;
  s.setProperty("color", "green", "important");
  s.setProperty("color", "red");
  assert_equals(s.getPropertyPriority("color"), "", "priority clears when re-set without it");
}, "re-setting a property drops its priority");

test(function () {
  var s = el().style;
  s.color = "red";
  s.removeProperty("color");
  assert_equals(s.getPropertyValue("color"), "", "removed property serialises empty");
  assert_equals(s.color, "", "removed property empty via IDL attribute");
}, "removeProperty");

test(function () {
  var s = el().style;
  s.setProperty("color", "red");
  s.setProperty("margin-top", "1px");
  assert_equals(s.length, 2, "length counts declared longhand properties");
  assert_in_array(s.item(0), ["color", "margin-top"], "item(0) names a property");
}, "length and item()");

test(function () {
  var s = el().style;
  s.setProperty("padding", "1px");
  // CSSOM stores a shorthand as its longhands
  assert_equals(s.length, 4, "the padding shorthand expands to four longhands");
}, "shorthand contributes its longhands to length");

test(function () {
  var s = el().style;
  s.setProperty("color", "red");
  assert_equals(s.cssText, "color: red;", "single declaration serialises with trailing ;");
}, "cssText serialisation of one property");

test(function () {
  var s = el().style;
  s.setProperty("color", "red");
  s.setProperty("padding", "1px", "important");
  assert_equals(s.cssText, "color: red; padding: 1px !important;");
}, "cssText serialisation with a priority");

test(function () {
  var s = el().style;
  s.cssText = "color: red; margin-top: 5px";
  assert_equals(s.color, "red");
  assert_equals(s.marginTop, "5px");
}, "cssText setter parses declarations");

test(function () {
  var s = el().style;
  s.cssText = "color: red; margin-top: 5px";
  assert_equals(s.cssText, "color: red; margin-top: 5px;",
    "cssText getter re-serialises with a trailing semicolon");
}, "cssText round-trips through re-serialisation");

test(function () {
  var s = el().style;
  s.setProperty("--custom", "3");
  assert_equals(s.getPropertyValue("--custom"), "3", "custom properties preserve case + value");
}, "custom property (variable) set / get");

test(function () {
  var e = el();
  e.style.color = "red";
  e.setAttribute("style", "");
  assert_equals(e.style.color, "", "clearing the style attribute clears the declaration");
}, "the style IDL attribute reflects the style content attribute");

test(function () {
  var s = el().style;
  assert_equals(s.getPropertyValue("color"), "", "unset property is the empty string, not null");
}, "unset property getPropertyValue is empty string");
