"""Tests for the validator.js port.

The bulk is ``fixtures/validator/cases.json`` -- the ``valid`` / ``invalid``
arrays lifted from validatorjs/validator.js's own ``test/validators.test.js``
for every validator whose default-options block could be extracted mechanically.
Plus a few API-shape checks and the sanitizers/converters.
"""

import json
import math
import pathlib
import re
import unittest

from domonic_libs import validator

CASES = json.loads((pathlib.Path(__file__).parent / "fixtures" / "validator" / "cases.json").read_text())


class TestValidatorSpec(unittest.TestCase):
    pass


def _make(name, sample, expected):
    def test(self):
        fn = getattr(validator, name)
        self.assertEqual(bool(fn(sample)), expected, repr(sample))

    test.__name__ = "test_" + name + "_" + re.sub(r"\W+", "_", sample)[:40] + ("_ok" if expected else "_no")
    return test


_seen = {}
for _name, _spec in CASES.items():
    for _sample in _spec["valid"]:
        _t = _make(_name, _sample, True)
        _seen[_t.__name__] = _seen.get(_t.__name__, 0) + 1
        if _seen[_t.__name__] > 1:
            _t.__name__ += f"_{_seen[_t.__name__]}"
        setattr(TestValidatorSpec, _t.__name__, _t)
    for _sample in _spec["invalid"]:
        _t = _make(_name, _sample, False)
        _seen[_t.__name__] = _seen.get(_t.__name__, 0) + 1
        if _seen[_t.__name__] > 1:
            _t.__name__ += f"_{_seen[_t.__name__]}"
        setattr(TestValidatorSpec, _t.__name__, _t)


class TestValidatorApi(unittest.TestCase):
    def test_string_only_contract(self):
        with self.assertRaises(TypeError):
            validator.isEmail(123)

    def test_options_as_dict_or_kwargs(self):
        self.assertTrue(validator.isInt("-12", {"min": -20, "max": 0}))
        self.assertTrue(validator.isInt("-12", min=-20, max=0))
        self.assertFalse(validator.isInt("5", max=0))

    def test_contains_equals_matches(self):
        self.assertTrue(
            validator.contains("Hello hello", "hello", {"ignoreCase": True, "minOccurrences": 2})
        )
        self.assertTrue(validator.equals("abc", "abc"))
        self.assertTrue(validator.matches("abc123", r"^[a-z]+\d+$"))
        self.assertFalse(validator.matches("abc", r"\d+"))

    def test_checksum_validators(self):
        self.assertTrue(validator.isIBAN("DE89370400440532013000"))
        self.assertFalse(validator.isIBAN("DE89370400440532013001"))
        self.assertTrue(validator.isCreditCard("4111111111111111"))
        self.assertTrue(validator.isEAN("4006381333931"))
        self.assertTrue(validator.isISIN("US0378331005"))
        self.assertTrue(validator.isISBN("978-3-16-148410-0"))

    def test_iso_code_sets(self):
        self.assertTrue(validator.isISO31661Alpha2("GB"))
        self.assertFalse(validator.isISO31661Alpha2("XX"))
        self.assertTrue(validator.isISO4217("usd"))
        self.assertTrue(validator.isISO6391("en"))

    def test_locale_validators(self):
        self.assertTrue(validator.isAlpha("abcXYZ"))
        self.assertTrue(validator.isAlpha("äöü", "de-DE"))
        self.assertTrue(validator.isAlphanumeric("abc123"))
        with self.assertRaises(ValueError):
            validator.isAlpha("abc", "xx-XX")

    def test_sanitizers_and_converters(self):
        self.assertEqual(validator.blacklist("a-b-c", "-"), "abc")
        self.assertEqual(validator.whitelist("a1 b2", "ab"), "ab")
        self.assertEqual(
            validator.escape('<a href="/">x</a>'),
            "&lt;a href=&quot;&#x2F;&quot;&gt;x&lt;&#x2F;a&gt;",
        )
        self.assertEqual(validator.unescape("&lt;x&#x2F;&gt;"), "<x/>")
        self.assertEqual(validator.trim("  x  "), "x")
        self.assertEqual(validator.ltrim("..x", "."), "x")
        self.assertEqual(validator.rtrim("x..", "."), "x")
        self.assertEqual(validator.stripLow("a\x00\nb", keep_new_lines=True), "a\nb")
        self.assertTrue(validator.toBoolean("yes"))
        self.assertFalse(validator.toBoolean("yes", strict=True))
        self.assertEqual(validator.toInt("ff", 16), 255)
        self.assertTrue(math.isnan(validator.toInt("nope")))
        self.assertEqual(validator.toFloat("1.5"), 1.5)
        self.assertIsNotNone(validator.toDate("2026-08-31"))
        self.assertIsNone(validator.toDate("not a date"))
        self.assertEqual(
            validator.normalizeEmail("Foo.Bar+tag@googlemail.com"), "foobar@gmail.com"
        )

    def test_namespace_completeness(self):
        # a broad sample of validator.js names must be present
        for name in ("isEmail", "isURL", "isIBAN", "isCreditCard", "isJWT", "isMACAddress",
                     "isStrongPassword", "isRFC3339", "isBase58", "isEthereumAddress"):
            self.assertTrue(callable(getattr(validator, name)))


if __name__ == "__main__":
    unittest.main()
