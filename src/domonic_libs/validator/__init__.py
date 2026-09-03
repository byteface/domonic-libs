# Ported from validatorjs/validator.js (MIT). Preserve the upstream licence when
# redistributing. One module per validator upstream; consolidated here, function
# names kept identical (camelCase) so ``validator.isEmail(...)`` matches.
"""Python port of validator.js -- string validators and sanitizers.

    from domonic_libs import validator
    validator.isEmail("ada@example.com")   # True
    validator.isIBAN("DE89370400440532013000")

Options are accepted either as a dict (like validator.js) or as keyword
arguments. Locale-parametrised validators that need large per-country tables
(``isMobilePhone``, ``isPostalCode``, ``isIdentityCard``, ``isTaxID``,
``isPassportNumber``, ``isVAT``, ``isLicensePlate``) are not ported yet;
``normalizeEmail`` is ported in reduced form (no provider domain lists).

marked's ``domonic.javascript`` regex gap (see ``docs/domonic-wrinkles.md``)
applies here too -- this port uses Python's ``re``.
"""

from __future__ import annotations

import math
import re

from . import _data

version = "13.15.35"

# ---------------------------------------------------------------------------
# util
# ---------------------------------------------------------------------------


def _assert_string(value):
    if value is None or not isinstance(value, str):
        received = "None" if value is None else type(value).__name__
        raise TypeError(f"Expected a string but received a {received}")
    return value


def _merge(options, defaults):
    merged = dict(defaults)
    if isinstance(options, dict):
        for key, value in options.items():
            if value is not None:
                merged[key] = value
    return merged


def _opts(options, kwargs, defaults):
    merged = dict(defaults)
    if isinstance(options, dict):
        merged.update({k: v for k, v in options.items() if v is not None})
    merged.update({k: v for k, v in kwargs.items() if v is not None})
    return merged


def _to_string(value):
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _re_escape_class(chars):
    return re.sub(r"[-[\]{}()*+?.,\\^$|#\s]", lambda m: "\\" + m.group(0), chars)


def _parse_int(value, radix=10):
    value = value.strip()
    match = re.match(r"^[+-]?", value)
    sign = -1 if match.group(0) == "-" else 1
    body = value[match.end():]
    if radix == 16 and body[:2].lower() == "0x":
        body = body[2:]
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"[:radix]
    taken = ""
    for ch in body.lower():
        if ch in digits:
            taken += ch
        else:
            break
    if not taken:
        return math.nan
    return sign * int(taken, radix)


_FLOAT_HEAD = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


def _parse_float(value):
    match = _FLOAT_HEAD.match(value.strip())
    if not match:
        return math.nan
    try:
        return float(match.group(0))
    except ValueError:
        return math.nan


# ---------------------------------------------------------------------------
# core
# ---------------------------------------------------------------------------


def contains(value, elem, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {"ignoreCase": False, "minOccurrences": 1})
    needle = _to_string(elem)
    if o["ignoreCase"]:
        return len(value.lower().split(needle.lower())) > o["minOccurrences"]
    return len(value.split(needle)) > o["minOccurrences"]


def equals(value, comparison):
    _assert_string(value)
    return value == comparison


def matches(value, pattern, modifiers=""):
    _assert_string(value)
    if hasattr(pattern, "test") and not isinstance(pattern, re.Pattern):
        return bool(pattern.test(value))  # domonic.javascript.RegExp
    if not isinstance(pattern, re.Pattern):
        flags = 0
        if "i" in modifiers:
            flags |= re.I
        if "m" in modifiers:
            flags |= re.M
        if "s" in modifiers:
            flags |= re.S
        pattern = re.compile(pattern, flags)
    return pattern.search(value) is not None


# ---------------------------------------------------------------------------
# numbers
# ---------------------------------------------------------------------------

_INT = re.compile(r"^(?:[-+]?(?:0|[1-9][0-9]*))$")
_INT_LEADING_ZEROES = re.compile(r"^[-+]?[0-9]+$")


def isInt(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    regex = _INT if o.get("allow_leading_zeroes") is False else _INT_LEADING_ZEROES
    if not regex.match(value):
        return False
    number = int(value)
    if "min" in o and o["min"] is not None and number < o["min"]:
        return False
    if "max" in o and o["max"] is not None and number > o["max"]:
        return False
    if "lt" in o and o["lt"] is not None and number >= o["lt"]:
        return False
    if "gt" in o and o["gt"] is not None and number <= o["gt"]:
        return False
    return True


def isFloat(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    sep = _data.DECIMAL[o["locale"]] if o.get("locale") else "."
    regex = re.compile(
        r"^(?:[-+])?(?:[0-9]+)?(?:%s[0-9]*)?(?:[eE][\+\-]?(?:[0-9]+))?$" % re.escape(sep)
    )
    if value in ("", ".", ",", "-", "+"):
        return False
    number = _parse_float(value.replace(",", "."))
    if not regex.match(value):
        return False
    if "min" in o and o["min"] is not None and not number >= o["min"]:
        return False
    if "max" in o and o["max"] is not None and not number <= o["max"]:
        return False
    if "lt" in o and o["lt"] is not None and not number < o["lt"]:
        return False
    if "gt" in o and o["gt"] is not None and not number > o["gt"]:
        return False
    return True


def isDecimal(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {"force_decimal": False, "decimal_digits": "1,", "locale": "en-US"})
    if o["locale"] not in _data.DECIMAL:
        raise ValueError(f"Invalid locale '{o['locale']}'")
    if value.replace(" ", "") in ("", "-", "+"):
        return False
    sep = re.escape(_data.DECIMAL[o["locale"]])
    q = "" if o["force_decimal"] else "?"
    regex = re.compile(r"^[-+]?([0-9]+)?(%s[0-9]{%s})%s$" % (sep, o["decimal_digits"], q))
    return regex.match(value) is not None


def isNumeric(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    if o.get("no_symbols"):
        return re.match(r"^[0-9]+$", value) is not None
    sep = _data.DECIMAL[o["locale"]] if o.get("locale") else "."
    return re.match(r"^[+-]?([0-9]*[%s])?[0-9]+$" % re.escape(sep), value) is not None


def isHexadecimal(value):
    _assert_string(value)
    return re.match(r"^(0x|0h)?[0-9A-F]+$", value, re.I) is not None


def isOctal(value):
    _assert_string(value)
    return re.match(r"^(0o)?[0-7]+$", value, re.I) is not None


def isDivisibleBy(value, number):
    _assert_string(value)
    return _to_float_or_nan(value) % int(number) == 0


def _to_float_or_nan(value):
    return toFloat(value)


def isPort(value):
    return isInt(value, {"allow_leading_zeroes": False, "min": 0, "max": 65535})


# ---------------------------------------------------------------------------
# strings / width
# ---------------------------------------------------------------------------


def isAscii(value):
    _assert_string(value)
    return re.match(r"^[\x00-\x7F]+$", value) is not None


_FULL_WIDTH = re.compile(r"[^ -~｡-ﾟﾠ-ￜ￨-￮0-9a-zA-Z]")
_HALF_WIDTH = re.compile(r"[ -~｡-ﾟﾠ-ￜ￨-￮0-9a-zA-Z]")


def isFullWidth(value):
    _assert_string(value)
    return _FULL_WIDTH.search(value) is not None


def isHalfWidth(value):
    _assert_string(value)
    return _HALF_WIDTH.search(value) is not None


def isVariableWidth(value):
    _assert_string(value)
    return _FULL_WIDTH.search(value) is not None and _HALF_WIDTH.search(value) is not None


def isMultibyte(value):
    _assert_string(value)
    return re.search(r"[^\x00-\x7F]", value) is not None


def isSurrogatePair(value):
    _assert_string(value)
    return re.search(r"[\uD800-\uDBFF][\uDC00-\uDFFF]", value) is not None


def isAlpha(value, locale="en-US", options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    ignore = o.get("ignore")
    if ignore is not None:
        if isinstance(ignore, re.Pattern):
            value = ignore.sub("", value)
        elif isinstance(ignore, str):
            value = re.sub("[%s]" % _re_escape_class(ignore), "", value)
        else:
            raise ValueError("ignore should be instance of a String or RegExp")
    if locale in _data.ALPHA:
        pattern, ci = _data.ALPHA[locale]
        return re.match(pattern, value, re.I if ci else 0) is not None
    raise ValueError(f"Invalid locale '{locale}'")


def isAlphanumeric(value, locale="en-US", options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    ignore = o.get("ignore")
    if ignore is not None:
        if isinstance(ignore, re.Pattern):
            value = ignore.sub("", value)
        elif isinstance(ignore, str):
            value = re.sub("[%s]" % _re_escape_class(ignore), "", value)
        else:
            raise ValueError("ignore should be instance of a String or RegExp")
    if locale in _data.ALPHANUMERIC:
        pattern, ci = _data.ALPHANUMERIC[locale]
        return re.match(pattern, value, re.I if ci else 0) is not None
    raise ValueError(f"Invalid locale '{locale}'")


def isLowercase(value):
    _assert_string(value)
    return value == value.lower()


def isUppercase(value):
    _assert_string(value)
    return value == value.upper()


def isEmpty(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {"ignore_whitespace": False})
    return (len(value.strip()) if o["ignore_whitespace"] else len(value)) == 0


def _presentation_and_surrogate_adjust(value):
    presentation = re.findall(r"[^️︎][️︎]", value)
    surrogates = re.findall(r"[\uD800-\uDBFF][\uDC00-\uDFFF]", value)
    return len(value) - len(presentation) - len(surrogates)


def isLength(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    minimum = o.get("min") or 0
    maximum = o.get("max")
    length = _presentation_and_surrogate_adjust(value)
    inside = length >= minimum and (maximum is None or length <= maximum)
    if inside and isinstance(o.get("discreteLengths"), (list, tuple)):
        return any(d == length for d in o["discreteLengths"])
    return inside


def _utf8_byte_length(value):
    return len(value.encode("utf-8", "replace"))


def isByteLength(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    minimum = o.get("min") or 0
    maximum = o.get("max")
    length = _utf8_byte_length(value)
    return length >= minimum and (maximum is None or length <= maximum)


# ---------------------------------------------------------------------------
# identifiers
# ---------------------------------------------------------------------------

_UUID = {
    "1": r"^[0-9A-F]{8}-[0-9A-F]{4}-1[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$",
    "2": r"^[0-9A-F]{8}-[0-9A-F]{4}-2[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$",
    "3": r"^[0-9A-F]{8}-[0-9A-F]{4}-3[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$",
    "4": r"^[0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$",
    "5": r"^[0-9A-F]{8}-[0-9A-F]{4}-5[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$",
    "6": r"^[0-9A-F]{8}-[0-9A-F]{4}-6[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$",
    "7": r"^[0-9A-F]{8}-[0-9A-F]{4}-7[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$",
    "8": r"^[0-9A-F]{8}-[0-9A-F]{4}-8[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$",
    "nil": r"^00000000-0000-0000-0000-000000000000$",
    "max": r"^ffffffff-ffff-ffff-ffff-ffffffffffff$",
    "loose": r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$",
    "all": r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}|00000000-0000-0000-0000-000000000000|ffffffff-ffff-ffff-ffff-ffffffffffff)$",
}


def isUUID(value, version=None):
    _assert_string(value)
    key = "all" if version is None else str(version)
    if key not in _UUID:
        return False
    return re.match(_UUID[key], value, re.I) is not None


def isULID(value):
    _assert_string(value)
    return re.match(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$", value, re.I) is not None


def isMongoId(value):
    _assert_string(value)
    return isHexadecimal(value) and len(value) == 24


def isSlug(value):
    _assert_string(value)
    return re.match(r"^[a-z0-9](?!.*[-_]{2,})(?:[a-z0-9_-]*[a-z0-9])?$", value) is not None


_HASH_LENGTHS = {
    "md5": 32, "md4": 32, "sha1": 40, "sha256": 64, "sha384": 96, "sha512": 128,
    "ripemd128": 32, "ripemd160": 40, "tiger128": 32, "tiger160": 40, "tiger192": 48,
    "crc32": 8, "crc32b": 8,
}


def isHash(value, algorithm):
    _assert_string(value)
    length = _HASH_LENGTHS.get(algorithm)
    if length is None:
        return False
    return re.match(r"^[a-fA-F0-9]{%d}$" % length, value) is not None


def isMD5(value):
    _assert_string(value)
    return re.match(r"^[a-f0-9]{32}$", value) is not None


def isJWT(value):
    _assert_string(value)
    parts = value.split(".")
    if len(parts) != 3:
        return False
    return all(isBase64(p, {"urlSafe": True}) for p in parts)


def isSemVer(value):
    _assert_string(value)
    pattern = (
        r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
        r"(?:-((?:0|[1-9]\d*|\d*[a-z-][0-9a-z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-z-][0-9a-z-]*))*))"
        r"?(?:\+([0-9a-z-]+(?:\.[0-9a-z-]+)*))?$"
    )
    return re.match(pattern, value, re.I) is not None


def isMACAddress(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    eui = str(o["eui"]) if o.get("eui") is not None else None
    no_sep = o.get("no_colons") or o.get("no_separators")
    m48 = r"^(?:[0-9a-fA-F]{2}([-:\s]))([0-9a-fA-F]{2}\1){4}([0-9a-fA-F]{2})$"
    m48_dots = r"^([0-9a-fA-F]{4}\.){2}([0-9a-fA-F]{4})$"
    m48_none = r"^([0-9a-fA-F]){12}$"
    m64 = r"^(?:[0-9a-fA-F]{2}([-:\s]))([0-9a-fA-F]{2}\1){6}([0-9a-fA-F]{2})$"
    m64_dots = r"^([0-9a-fA-F]{4}\.){3}([0-9a-fA-F]{4})$"
    m64_none = r"^([0-9a-fA-F]){16}$"
    if no_sep:
        if eui == "48":
            return re.match(m48_none, value) is not None
        if eui == "64":
            return re.match(m64_none, value) is not None
        return re.match(m48_none, value) is not None or re.match(m64_none, value) is not None
    if eui == "48":
        return re.match(m48, value) is not None or re.match(m48_dots, value) is not None
    if eui == "64":
        return re.match(m64, value) is not None or re.match(m64_dots, value) is not None
    return isMACAddress(value, {"eui": "48"}) or isMACAddress(value, {"eui": "64"})


def isIMEI(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    if o.get("allow_hyphens"):
        regex = r"^\d{2}-\d{6}-\d{6}-\d{1}$"
    else:
        regex = r"^[0-9]{15}$"
    if not re.match(regex, value):
        return False
    digits = value.replace("-", "")
    total = 0
    mul = 2
    for i in range(14):
        d = int(digits[14 - i - 1]) * mul
        total += (d % 10 + 1) if d >= 10 else d
        mul = 1 if mul == 2 else 2
    return (10 - total % 10) % 10 == int(digits[14])


def isEthereumAddress(value):
    _assert_string(value)
    return re.match(r"^(0x)[0-9a-f]{40}$", value, re.I) is not None


def isBtcAddress(value):
    _assert_string(value)
    bech32 = r"^(bc1|tb1|bc1p|tb1p)[ac-hj-np-z02-9]{39,58}$"
    base58 = r"^(1|2|3|m)[A-HJ-NP-Za-km-z1-9]{25,39}$"
    return re.match(bech32, value) is not None or re.match(base58, value) is not None


def isAbaRouting(value):
    _assert_string(value)
    regex = r"^(?!(1[3-9])|(20)|(3[3-9])|(4[0-9])|(5[0-9])|(60)|(7[3-9])|(8[1-9])|(9[0-2])|(9[3-9]))[0-9]{9}$"
    if not re.match(regex, value):
        return False
    total = 0
    for i, ch in enumerate(value):
        weight = (3, 7, 1)[i % 3]
        total += int(ch) * weight
    return total % 10 == 0


# ---------------------------------------------------------------------------
# Luhn / cards / financial
# ---------------------------------------------------------------------------


def isLuhnNumber(value):
    _assert_string(value)
    sanitized = re.sub(r"[- ]+", "", value)
    if not sanitized.isdigit():
        return False
    total = 0
    should_double = False
    for ch in reversed(sanitized):
        n = int(ch)
        if should_double:
            n *= 2
            total += (n % 10 + 1) if n >= 10 else n
        else:
            total += n
        should_double = not should_double
    return bool(sanitized) and total % 10 == 0


_CARDS = {
    "amex": r"^3[47][0-9]{13}$",
    "dinersclub": r"^3(?:0[0-5]|[68][0-9])[0-9]{11}$",
    "discover": r"^6(?:011|5[0-9][0-9])[0-9]{12,15}$",
    "jcb": r"^(?:2131|1800|35\d{3})\d{11}$",
    "mastercard": r"^5[1-5][0-9]{2}|(222[1-9]|22[3-9][0-9]|2[3-6][0-9]{2}|27[01][0-9]|2720)[0-9]{12}$",
    "unionpay": r"^(6[27][0-9]{14}|^(81[0-9]{14,17}))$",
    "visa": r"^(?:4[0-9]{12})(?:[0-9]{3,6})?$",
}


def isCreditCard(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    provider = o.get("provider")
    sanitized = re.sub(r"[- ]+", "", value)
    if provider and provider.lower() in _CARDS:
        if not re.match(_CARDS[provider.lower()], sanitized):
            return False
    elif provider and provider.lower() not in _CARDS:
        raise ValueError(f"{provider} is not a valid credit card provider.")
    elif not any(re.match(rx, sanitized) for rx in _CARDS.values()):
        return False
    return isLuhnNumber(value)


def isISIN(value):
    _assert_string(value)
    if not re.match(r"^[A-Z]{2}[0-9A-Z]{9}[0-9]$", value):
        return False
    double = True
    total = 0
    for i in range(len(value) - 2, -1, -1):
        ch = value[i]
        if "A" <= ch <= "Z":
            v = ord(ch) - 55
            parts = [v % 10, v // 10]
        else:
            parts = [ord(ch) - ord("0")]
        for digit in parts:
            if double:
                total += (1 + (digit - 5) * 2) if digit >= 5 else digit * 2
            else:
                total += digit
            double = not double
    check = (((total + 9) // 10) * 10) - total
    return int(value[-1]) == check


def isEAN(value):
    _assert_string(value)
    if not re.match(r"^(\d{8}|\d{13}|\d{14})$", value):
        return False
    length = len(value)

    def weight(index):
        if length in (8, 14):
            return 3 if index % 2 == 0 else 1
        return 1 if index % 2 == 0 else 3

    checksum = sum(int(ch) * weight(i) for i, ch in enumerate(value[:-1]))
    remainder = 10 - checksum % 10
    expected = remainder if remainder < 10 else 0
    return int(value[-1]) == expected


def isISBN(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    version = str(o["version"]) if o.get("version") else (str(options) if isinstance(options, (str, int)) else "")
    if not version:
        return isISBN(value, {"version": 10}) or isISBN(value, {"version": 13})
    sanitized = re.sub(r"[\s-]+", "", value)
    checksum = 0
    if version == "10":
        if not re.match(r"^(?:[0-9]{9}X|[0-9]{10})$", sanitized):
            return False
        for i in range(9):
            checksum += (i + 1) * int(sanitized[i])
        checksum += 100 if sanitized[9] == "X" else 10 * int(sanitized[9])
        return checksum % 11 == 0
    if version == "13":
        if not re.match(r"^(?:[0-9]{13})$", sanitized):
            return False
        factor = (1, 3)
        for i in range(12):
            checksum += factor[i % 2] * int(sanitized[i])
        return int(sanitized[12]) - ((10 - checksum % 10) % 10) == 0
    return False


def isISSN(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    pattern = r"^\d{4}-?\d{3}[\dX]$"
    if o.get("require_hyphen"):
        pattern = pattern.replace("?", "")
    flags = 0 if o.get("case_sensitive") else re.I
    if not re.match(pattern, value, flags):
        return False
    digits = value.replace("-", "").upper()
    checksum = sum((10 if d == "X" else int(d)) * (8 - i) for i, d in enumerate(digits))
    return checksum % 11 == 0


def isISRC(value):
    _assert_string(value)
    return re.match(r"^[A-Z]{2}[0-9A-Z]{3}\d{2}\d{5}$", value) is not None


def isIBAN(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    stripped = re.sub(r"[\s\-]+", "", value).upper()
    code = stripped[:2]

    if o.get("whitelist"):
        if any(c not in _data.IBAN_REGEX for c in o["whitelist"]):
            return False
        if code not in o["whitelist"]:
            return False
    if o.get("blacklist") and code in o["blacklist"]:
        return False

    if code not in _data.IBAN_REGEX or not re.match(_data.IBAN_REGEX[code], stripped):
        return False

    rearranged = stripped[4:] + stripped[:4]
    converted = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    remainder = 0
    for chunk in re.findall(r"\d{1,7}", converted):
        remainder = int(str(remainder) + chunk) % 97
    return remainder == 1


def isBIC(value):
    _assert_string(value)
    country = value[4:6].upper()
    if country not in _data.ISO_31661_ALPHA2 and country != "XK":
        return False
    return re.match(r"^[A-Za-z]{6}[A-Za-z0-9]{2}([A-Za-z0-9]{3})?$", value) is not None


def isCurrency(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {
        "symbol": "$", "require_symbol": False, "allow_space_after_symbol": False,
        "symbol_after_digits": False, "allow_negatives": True, "parens_for_negatives": False,
        "negative_sign_before_digits": False, "negative_sign_after_digits": False,
        "allow_negative_sign_placeholder": False, "thousands_separator": ",",
        "decimal_separator": ".", "allow_decimal": True, "require_decimal": False,
        "digits_after_decimal": [2], "allow_space_after_digits": False,
    })
    decimal_digits = "|".join(r"\d{%s}" % d for d in o["digits_after_decimal"])
    symbol = "(%s)%s" % (
        re.sub(r"\W", lambda m: "\\" + m.group(0), o["symbol"]),
        "" if o["require_symbol"] else "?",
    )
    negative = "-?"
    without_sep = r"[1-9]\d*"
    with_sep = r"[1-9]\d{0,2}(\%s\d{3})*" % o["thousands_separator"]
    whole = "(%s)?" % "|".join(["0", without_sep, with_sep])
    decimal_amount = r"(\%s(%s))%s" % (
        o["decimal_separator"], decimal_digits, "" if o["require_decimal"] else "?"
    )
    pattern = whole + (decimal_amount if (o["allow_decimal"] or o["require_decimal"]) else "")
    if o["allow_negatives"] and not o["parens_for_negatives"]:
        if o["negative_sign_after_digits"]:
            pattern += negative
        elif o["negative_sign_before_digits"]:
            pattern = negative + pattern
    if o["allow_negative_sign_placeholder"]:
        pattern = r"( (?!\-))?" + pattern
    elif o["allow_space_after_symbol"]:
        pattern = " ?" + pattern
    elif o["allow_space_after_digits"]:
        pattern += "( (?!$))?"
    if o["symbol_after_digits"]:
        pattern += symbol
    else:
        pattern = symbol + pattern
    if o["allow_negatives"]:
        if o["parens_for_negatives"]:
            pattern = r"(\(%s\)|%s)" % (pattern, pattern)
        elif not (o["negative_sign_before_digits"] or o["negative_sign_after_digits"]):
            pattern = negative + pattern
    return re.match(r"^(?!-? )(?=.*\d)%s$" % pattern, value) is not None


# ---------------------------------------------------------------------------
# network
# ---------------------------------------------------------------------------

_IPV4_SEG = r"(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])"
_IPV4 = r"(%s[.]){3}%s" % (_IPV4_SEG, _IPV4_SEG)
_IPV4_RE = re.compile(r"^%s$" % _IPV4)
_IPV6_SEG = r"(?:[0-9a-fA-F]{1,4})"
_IPV6_RE = re.compile(
    "^("
    + r"(?:%s:){7}(?:%s|:)|" % (_IPV6_SEG, _IPV6_SEG)
    + r"(?:%s:){6}(?:%s|:%s|:)|" % (_IPV6_SEG, _IPV4, _IPV6_SEG)
    + r"(?:%s:){5}(?::%s|(:%s){1,2}|:)|" % (_IPV6_SEG, _IPV4, _IPV6_SEG)
    + r"(?:%s:){4}(?:(:%s){0,1}:%s|(:%s){1,3}|:)|" % (_IPV6_SEG, _IPV6_SEG, _IPV4, _IPV6_SEG)
    + r"(?:%s:){3}(?:(:%s){0,2}:%s|(:%s){1,4}|:)|" % (_IPV6_SEG, _IPV6_SEG, _IPV4, _IPV6_SEG)
    + r"(?:%s:){2}(?:(:%s){0,3}:%s|(:%s){1,5}|:)|" % (_IPV6_SEG, _IPV6_SEG, _IPV4, _IPV6_SEG)
    + r"(?:%s:){1}(?:(:%s){0,4}:%s|(:%s){1,6}|:)|" % (_IPV6_SEG, _IPV6_SEG, _IPV4, _IPV6_SEG)
    + r"(?::((?::%s){0,5}:%s|(?::%s){1,7}|:))" % (_IPV6_SEG, _IPV4, _IPV6_SEG)
    + r")(%[0-9a-zA-Z.]{1,})?$"
)


def isIP(value, version=None, **kwargs):
    _assert_string(value)
    if isinstance(version, dict):
        version = version.get("version")
    if version is None:
        version = kwargs.get("version")
    if not version:
        return isIP(value, 4) or isIP(value, 6)
    if str(version) == "4":
        return _IPV4_RE.match(value) is not None
    if str(version) == "6":
        return _IPV6_RE.match(value) is not None
    return False


def isIPRange(value, version=""):
    _assert_string(value)
    parts = value.split("/")
    if len(parts) != 2:
        return False
    if not re.match(r"^\d{1,3}$", parts[1]):
        return False
    if len(parts[1]) > 1 and parts[1].startswith("0"):
        return False
    if not isIP(parts[0], version):
        return False
    if str(version) == "4":
        expected = 32
    elif str(version) == "6":
        expected = 128
    else:
        expected = 128 if isIP(parts[0], 6) else 32
    return 0 <= int(parts[1]) <= expected


_FQDN_DEFAULTS = {
    "require_tld": True, "allow_underscores": False, "allow_trailing_dot": False,
    "allow_numeric_tld": False, "allow_wildcard": False, "ignore_max_length": False,
}


def isFQDN(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, _FQDN_DEFAULTS)
    if o["allow_trailing_dot"] and value.endswith("."):
        value = value[:-1]
    if o["allow_wildcard"] and value.startswith("*."):
        value = value[2:]
    parts = value.split(".")
    tld = parts[-1]
    if o["require_tld"]:
        if len(parts) < 2:
            return False
        if not o["allow_numeric_tld"] and not re.match(
            r"^([a-z¡-¨ª-퟿豈-﷏ﷰ-￯]{2,}|xn[a-z0-9-]{2,})$",
            tld, re.I,
        ):
            return False
        if re.search(r"\s", tld):
            return False
    if not o["allow_numeric_tld"] and re.match(r"^\d+$", tld):
        return False
    for part in parts:
        if len(part) > 63 and not o["ignore_max_length"]:
            return False
        if not re.match(r"^[a-z_¡-￿0-9-]+$", part, re.I):
            return False
        if re.search(r"[！-～]", part):
            return False
        if re.search(r"^-|-$", part):
            return False
        if not o["allow_underscores"] and "_" in part:
            return False
    return True


_URL_DEFAULTS = {
    "protocols": ["http", "https", "ftp"], "require_tld": True, "require_protocol": False,
    "require_host": True, "require_port": False, "require_valid_protocol": True,
    "allow_underscores": False, "allow_trailing_dot": False,
    "allow_protocol_relative_urls": False, "allow_fragments": True,
    "allow_query_components": True, "validate_length": True, "max_allowed_length": 2084,
}


def isURL(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, _URL_DEFAULTS)
    if not value or re.search(r"[\s<>]", value):
        return False
    if value.startswith("mailto:"):
        return False
    if o["validate_length"] and len(value) > o["max_allowed_length"]:
        return False
    if not o["allow_fragments"] and "#" in value:
        return False
    if not o["allow_query_components"] and ("?" in value or "&" in value):
        return False

    url = value.split("#")[0].split("?")[0]

    protocol_match = re.match(r"^([a-z][a-z0-9+\-.]*):", url, re.I)
    had_explicit_protocol = False
    if protocol_match:
        potential = protocol_match.group(1)
        after = url[protocol_match.end():]
        starts_slashes = after[:2] == "//"

        def consume_protocol():
            nonlocal had_explicit_protocol
            had_explicit_protocol = True
            proto = potential.lower()
            if o["require_valid_protocol"] and proto not in o["protocols"]:
                return False
            return url[protocol_match.end():]

        if not starts_slashes:
            first_slash = after.find("/")
            before_slash = after if first_slash == -1 else after[:first_slash]
            at = before_slash.find("@")
            if at != -1:
                before_at = before_slash[:at]
                valid_auth = re.match(r"^[a-zA-Z0-9\-_.%:]*$", before_at) is not None
                has_encoded = re.search(r"%[0-9a-fA-F]{2}", before_at) is not None
                if valid_auth and not has_encoded:
                    if o["require_protocol"]:
                        return False
                else:
                    r = consume_protocol()
                    if r is False:
                        return False
                    url = r
            else:
                looks_like_port = re.match(r"^[0-9]", after) is not None
                if looks_like_port:
                    if o["require_protocol"]:
                        return False
                else:
                    r = consume_protocol()
                    if r is False:
                        return False
                    url = r
        else:
            r = consume_protocol()
            if r is False:
                return False
            url = r
    elif o["require_protocol"]:
        return False

    if url[:2] == "//":
        if not had_explicit_protocol and not o["allow_protocol_relative_urls"]:
            return False
        url = url[2:]

    if url == "":
        return False

    url = url.split("/")[0]
    if url == "" and not o["require_host"]:
        return True

    at_split = url.split("@")
    if len(at_split) > 1:
        if o.get("disallow_auth"):
            return False
        if at_split[0] == "":
            return False
        auth = at_split[0]
        rest = at_split[1:]
        if ":" in auth and len(auth.split(":")) > 2:
            return False
        user_pass = auth.split(":")
        user = user_pass[0]
        password = user_pass[1] if len(user_pass) > 1 else None
        if user == "" and password == "":
            return False
        hostname = "@".join(rest)
    else:
        hostname = url

    ipv6 = None
    port_str = None
    ipv6_match = re.match(r"^\[([^\]]+)\](?::([0-9]+))?$", hostname)
    if ipv6_match:
        host = ""
        ipv6 = ipv6_match.group(1)
        port_str = ipv6_match.group(2)
    else:
        seg = hostname.split(":")
        host = seg[0]
        if len(seg) > 1:
            port_str = ":".join(seg[1:])

    if port_str is not None and len(port_str) > 0:
        if not re.match(r"^[0-9]+$", port_str):
            return False
        port = int(port_str)
        if port <= 0 or port > 65535:
            return False
    elif o["require_port"]:
        return False

    if o.get("host_whitelist"):
        return _check_host(host, o["host_whitelist"])

    if host == "" and not o["require_host"]:
        return True

    if not isIP(host) and not isFQDN(host, o) and not (ipv6 and isIP(ipv6, 6)):
        return False

    host = host or ipv6
    if o.get("host_blacklist") and _check_host(host, o["host_blacklist"]):
        return False
    return True


def _check_host(host, matches):
    for m in matches:
        if host == m or (isinstance(m, re.Pattern) and m.search(host)):
            return True
    return False


# ---------------------------------------------------------------------------
# email
# ---------------------------------------------------------------------------

_EMAIL_DEFAULTS = {
    "allow_display_name": False, "allow_underscores": False, "require_display_name": False,
    "allow_utf8_local_part": True, "require_tld": True, "blacklisted_chars": "",
    "ignore_max_length": False, "host_blacklist": [], "host_whitelist": [],
}
_SPLIT_NAME_ADDRESS = re.compile(r"^([^\x00-\x1F\x7F-\x9F]+)<", re.I)
_EMAIL_USER = re.compile(r"^[a-z\d!#$%&'*+\-/=?^_`{|}~]+$", re.I)
_EMAIL_USER_UTF8 = re.compile(
    r"^[a-z\d!#$%&'*+\-/=?^_`{|}~¡-퟿豈-﷏ﷰ-￯]+$", re.I
)
_QUOTED_USER = re.compile(
    r"^([\s\x01-\x08\x0b\x0c\x0e-\x1f\x7f\x21\x23-\x5b\x5d-\x7e]|(\\[\x01-\x09\x0b\x0c\x0d-\x7f]))*$",
    re.I,
)
_QUOTED_USER_UTF8 = re.compile(
    r"^([\s\x01-\x08\x0b\x0c\x0e-\x1f\x7f\x21\x23-\x5b\x5d-\x7e -퟿豈-﷏ﷰ-￯]|(\\[\x01-\x09\x0b\x0c\x0d-\x7f -퟿豈-﷏ﷰ-￯]))*$",
    re.I,
)


def _validate_display_name(name):
    without_quotes = re.sub(r'^"(.+)"$', lambda m: m.group(1), name)
    if not without_quotes.strip():
        return False
    if re.search(r'[.";<>]', without_quotes):
        if without_quotes == name:
            return False
        if len(without_quotes.split('"')) != len(without_quotes.split('\\"')):
            return False
    return True


def isEmail(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, _EMAIL_DEFAULTS)

    if o["require_display_name"] or o["allow_display_name"]:
        match = _SPLIT_NAME_ADDRESS.match(value)
        if match:
            display_name = match.group(1)
            value = value.replace(display_name, "", 1)
            value = re.sub(r"(^<|>$)", "", value)
            if display_name.endswith(" "):
                display_name = display_name[:-1]
            if not _validate_display_name(display_name):
                return False
        elif o["require_display_name"]:
            return False

    if not o["ignore_max_length"] and len(value) > 254:
        return False

    parts = value.split("@")
    domain = parts.pop()
    lower_domain = domain.lower()

    if o["host_blacklist"] and _check_host(lower_domain, o["host_blacklist"]):
        return False
    if o["host_whitelist"] and not _check_host(lower_domain, o["host_whitelist"]):
        return False

    user = "@".join(parts)

    if not o["ignore_max_length"] and (
        not isByteLength(user, {"max": 64}) or not isByteLength(domain, {"max": 254})
    ):
        return False

    if not isFQDN(domain, {
        "require_tld": o["require_tld"],
        "ignore_max_length": o["ignore_max_length"],
        "allow_underscores": o["allow_underscores"],
    }):
        if not o.get("allow_ip_domain"):
            return False
        if not isIP(domain):
            if not (domain.startswith("[") and domain.endswith("]")):
                return False
            inner = domain[1:-1]
            if not inner or not isIP(inner):
                return False

    if o["blacklisted_chars"]:
        if re.search("[%s]+" % o["blacklisted_chars"], user):
            return False

    if len(user) >= 2 and user[0] == '"' and user[-1] == '"':
        user = user[1:-1]
        return (_QUOTED_USER_UTF8 if o["allow_utf8_local_part"] else _QUOTED_USER).match(user) is not None

    pattern = _EMAIL_USER_UTF8 if o["allow_utf8_local_part"] else _EMAIL_USER
    return all(pattern.match(part) for part in user.split("."))


def isMailtoURI(value, options=None, **kwargs):
    _assert_string(value)
    if not value.startswith("mailto:"):
        return False
    body = value[len("mailto:"):]
    to, _, query = body.partition("?")
    if not to and not query:
        return True

    allowed = {"subject", "body", "cc", "bcc"}
    q = {"cc": "", "bcc": ""}
    params = query.split("&") if query else []
    if len(params) > 4:
        return False
    for entry in params:
        key, _, val = entry.partition("=")
        if key and key not in allowed:
            return False
        if val and key in ("cc", "bcc"):
            q[key] = val
        if key:
            allowed.discard(key)

    for email in f"{to},{q['cc']},{q['bcc']}".split(","):
        email = email.strip(" ")
        if email and not isEmail(email, options if isinstance(options, dict) else kwargs):
            return False
    return True


# ---------------------------------------------------------------------------
# URIs / colours / misc
# ---------------------------------------------------------------------------


def isDataURI(value):
    _assert_string(value)
    data = value.split(",")
    if len(data) < 2:
        return False
    attributes = data.pop(0).strip().split(";")
    scheme_media = attributes.pop(0)
    if scheme_media[:5] != "data:":
        return False
    media_type = scheme_media[5:]
    if media_type != "" and not re.match(r"^[a-z]+\/[a-z0-9\-\+\._]+$", media_type, re.I):
        return False
    for i, attr in enumerate(attributes):
        if not (i == len(attributes) - 1 and attr.lower() == "base64") and not re.match(
            r"^[a-z\-]+=[a-z0-9\-]+$", attr, re.I
        ):
            return False
    for chunk in data:
        if not re.match(r"^[a-z0-9!\$&'\(\)\*\+,;=\-\._~:@\/\?%\s]*$", chunk, re.I):
            return False
    return True


def isMagnetURI(value):
    _assert_string(value)
    if not value.startswith("magnet:?"):
        return False
    pattern = (
        r"(?:^magnet:\?|[^?&]&)xt(?:\.1)?=urn:(?:(?:aich|bitprint|btih|ed2k|ed2khash|kzhash"
        r"|md5|sha1|tree:tiger):[a-z0-9]{32}(?:[a-z0-9]{8})?|btmh:1220[a-z0-9]{64})(?:$|&)"
    )
    return re.search(pattern, value, re.I) is not None


def isMimeType(value):
    _assert_string(value)
    simple = r"^(application|audio|font|image|message|model|multipart|text|video)\/[a-zA-Z0-9\.\-\+_]{1,100}$"
    text = r"^text\/[a-zA-Z0-9\.\-\+]{1,100};\s?charset=(\"[a-zA-Z0-9\.\-\+\s]{0,70}\"|[a-zA-Z0-9\.\-\+]{0,70})(\s?\([a-zA-Z0-9\.\-\+\s]{1,20}\))?$"
    multipart = r"^multipart\/[a-zA-Z0-9\.\-\+]{1,100}(;\s?(boundary|charset)=(\"[a-zA-Z0-9\.\-\+\s]{0,70}\"|[a-zA-Z0-9\.\-\+]{0,70})(\s?\([a-zA-Z0-9\.\-\+\s]{1,20}\))?){0,2}$"
    return any(re.match(rx, value, re.I) for rx in (simple, text, multipart))


def isHexColor(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {"require_hashtag": False})
    if o["require_hashtag"]:
        return re.match(r"^#([0-9A-F]{3}|[0-9A-F]{4}|[0-9A-F]{6}|[0-9A-F]{8})$", value, re.I) is not None
    return re.match(r"^#?([0-9A-F]{3}|[0-9A-F]{4}|[0-9A-F]{6}|[0-9A-F]{8})$", value, re.I) is not None


_RGB = r"^rgb\((([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5]),){2}([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])\)$"
_RGBA = r"^rgba\((([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5]),){3}(0?\.\d+|1(\.0+)?|0(\.0+)?)\)$"
_RGB_PCT = r"^rgb\((([0-9]%|[1-9][0-9]%|100%),){2}([0-9]%|[1-9][0-9]%|100%)\)$"
_RGBA_PCT = r"^rgba\((([0-9]%|[1-9][0-9]%|100%),){3}(0?\.\d+|1(\.0+)?|0(\.0+)?)\)$"


def isRgbColor(value, options=None, **kwargs):
    _assert_string(value)
    allow_spaces = False
    include_percent = True
    if isinstance(options, dict):
        allow_spaces = options.get("allowSpaces", allow_spaces)
        include_percent = options.get("includePercentValues", include_percent)
    elif options is not None:
        include_percent = bool(options)
    if kwargs:
        allow_spaces = kwargs.get("allowSpaces", allow_spaces)
        include_percent = kwargs.get("includePercentValues", include_percent)
    if allow_spaces:
        if not re.match(r"^rgba?", value):
            return False
        value = re.sub(r"\s", "", value)
    if not include_percent:
        return re.match(_RGB, value) is not None or re.match(_RGBA, value) is not None
    return any(re.match(rx, value) is not None for rx in (_RGB, _RGBA, _RGB_PCT, _RGBA_PCT))


_HSL_COMMA = re.compile(
    r"^hsla?\(((\+|\-)?([0-9]+(\.[0-9]+)?(e(\+|\-)?[0-9]+)?|\.[0-9]+(e(\+|\-)?[0-9]+)?))(deg|grad|rad|turn)?(,(\+|\-)?([0-9]+(\.[0-9]+)?(e(\+|\-)?[0-9]+)?|\.[0-9]+(e(\+|\-)?[0-9]+)?)%){2}(,((\+|\-)?([0-9]+(\.[0-9]+)?(e(\+|\-)?[0-9]+)?|\.[0-9]+(e(\+|\-)?[0-9]+)?)%?))?\)$",
    re.I,
)
_HSL_SPACE = re.compile(
    r"^hsla?\(((\+|\-)?([0-9]+(\.[0-9]+)?(e(\+|\-)?[0-9]+)?|\.[0-9]+(e(\+|\-)?[0-9]+)?))(deg|grad|rad|turn)?(\s(\+|\-)?([0-9]+(\.[0-9]+)?(e(\+|\-)?[0-9]+)?|\.[0-9]+(e(\+|\-)?[0-9]+)?)%){2}\s?(\/\s((\+|\-)?([0-9]+(\.[0-9]+)?(e(\+|\-)?[0-9]+)?|\.[0-9]+(e(\+|\-)?[0-9]+)?)%?)\s?)?\)$",
    re.I,
)


def isHSL(value):
    _assert_string(value)
    stripped = re.sub(r"\s+", " ", value)
    stripped = re.sub(r"\s?(hsla?\(|\)|,)\s?", lambda m: m.group(1), stripped, flags=re.I)
    if "," in stripped:
        return _HSL_COMMA.match(stripped) is not None
    return _HSL_SPACE.match(stripped) is not None


def isLatLong(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {"checkDMS": False})
    if "," not in value:
        return False
    pair = value.split(",")
    if (pair[0].startswith("(") and not pair[1].endswith(")")) or (
        pair[1].endswith(")") and not pair[0].startswith("(")
    ):
        return False
    if o["checkDMS"]:
        lat_dms = r"^(([1-8]?\d)\D+([1-5]?\d|60)\D+([1-5]?\d|60)(\.\d+)?|90\D+0\D+0)\D+[NSns]?$"
        long_dms = r"^\s*([1-7]?\d{1,2}\D+([1-5]?\d|60)\D+([1-5]?\d|60)(\.\d+)?|180\D+0\D+0)\D+[EWew]?$"
        return re.match(lat_dms, pair[0], re.I) is not None and re.match(long_dms, pair[1], re.I) is not None
    lat = r"^\(?[+-]?(90(\.0+)?|[1-8]?\d(\.\d+)?)$"
    lon = r"^\s?[+-]?(180(\.0+)?|1[0-7]\d(\.\d+)?|\d{1,2}(\.\d+)?)\)?$"
    return re.match(lat, pair[0]) is not None and re.match(lon, pair[1]) is not None


def isBase32(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {"crockford": False})
    if o["crockford"]:
        return re.match(r"^[A-HJKMNP-TV-Z0-9]+$", value) is not None
    return len(value) % 8 == 0 and re.match(r"^[A-Z2-7]+=*$", value) is not None


def isBase58(value):
    _assert_string(value)
    return re.match(r"^[A-HJ-NP-Za-km-z1-9]*$", value) is not None


def isBase64(value, options=None, **kwargs):
    _assert_string(value)
    url_safe = bool((options or {}).get("urlSafe") if isinstance(options, dict) else kwargs.get("urlSafe"))
    o = _opts(options, kwargs, {"urlSafe": False, "padding": not url_safe})
    if value == "":
        return True
    if o["padding"] and len(value) % 4 != 0:
        return False
    if o["urlSafe"]:
        regex = r"^[A-Za-z0-9_-]+={0,2}$" if o["padding"] else r"^[A-Za-z0-9_-]+$"
    else:
        regex = r"^[A-Za-z0-9+/]+={0,2}$" if o["padding"] else r"^[A-Za-z0-9+/]+$"
    return (not o["padding"] or len(value) % 4 == 0) and re.match(regex, value) is not None


def isJSON(value, options=None, **kwargs):
    import json

    _assert_string(value)
    o = _opts(options, kwargs, {"allow_primitives": False})
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return False
    if o["allow_primitives"]:
        return True
    return isinstance(parsed, (dict, list))


def isStrongPassword(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {
        "minLength": 8, "minLowercase": 1, "minUppercase": 1, "minNumbers": 1, "minSymbols": 1,
        "returnScore": False, "pointsPerUnique": 1, "pointsPerRepeat": 0.5,
        "pointsForContainingLower": 10, "pointsForContainingUpper": 10,
        "pointsForContainingNumber": 10, "pointsForContainingSymbol": 10,
    })
    counts = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    lower = sum(v for c, v in counts.items() if re.match(r"^[a-z]$", c))
    upper = sum(v for c, v in counts.items() if re.match(r"^[A-Z]$", c))
    numbers = sum(v for c, v in counts.items() if re.match(r"^[0-9]$", c))
    symbols = sum(v for c, v in counts.items() if re.match(r"^[-#!$@£%^&*()_+|~=`{}\[\]:\";'<>?,.\/\\ ]$", c))
    if o["returnScore"]:
        points = len(counts) * o["pointsPerUnique"]
        points += (len(value) - len(counts)) * o["pointsPerRepeat"]
        points += o["pointsForContainingLower"] if lower else 0
        points += o["pointsForContainingUpper"] if upper else 0
        points += o["pointsForContainingNumber"] if numbers else 0
        points += o["pointsForContainingSymbol"] if symbols else 0
        return points
    return (
        len(value) >= o["minLength"]
        and lower >= o["minLowercase"]
        and upper >= o["minUppercase"]
        and numbers >= o["minNumbers"]
        and symbols >= o["minSymbols"]
    )


def isWhitelisted(value, chars):
    _assert_string(value)
    return all(ch in chars for ch in value)


def isIn(value, options):
    _assert_string(value)
    if isinstance(options, (list, tuple)):
        return _to_string_any(value) in [_to_string(o) for o in options]
    if isinstance(options, dict):
        return value in options
    if isinstance(options, str):
        return value in options
    return False


def _to_string_any(value):
    return value


def isBoolean(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {"loose": False})
    strict = ["true", "false", "1", "0"]
    if o["loose"]:
        return value.lower() in strict + ["yes", "no"]
    return value in strict


def isLocale(value):
    _assert_string(value)
    extlang = r"([A-Za-z]{3}(-[A-Za-z]{3}){0,2})"
    language = r"(([a-zA-Z]{2,3}(-%s)?)|([a-zA-Z]{5,8}))" % extlang
    script = r"([A-Za-z]{4})"
    region = r"([A-Za-z]{2}|\d{3})"
    variant = r"([A-Za-z0-9]{5,8}|(\d[A-Z-a-z0-9]{3}))"
    singleton = r"(\d|[A-W]|[Y-Z]|[a-w]|[y-z])"
    extension = r"(%s(-[A-Za-z0-9]{2,8})+)" % singleton
    privateuse = r"(x(-[A-Za-z0-9]{1,8})+)"
    irregular = (
        r"((en-GB-oed)|(i-ami)|(i-bnn)|(i-default)|(i-enochian)|(i-hak)|(i-klingon)"
        r"|(i-lux)|(i-mingo)|(i-navajo)|(i-pwn)|(i-tao)|(i-tay)|(i-tsu)|(sgn-BE-FR)"
        r"|(sgn-BE-NL)|(sgn-CH-DE))"
    )
    regular = (
        r"((art-lojban)|(cel-gaulish)|(no-bok)|(no-nyn)|(zh-guoyu)|(zh-hakka)|(zh-min)"
        r"|(zh-min-nan)|(zh-xiang))"
    )
    grandfathered = r"(%s|%s)" % (irregular, regular)
    delimiter = r"(-|_)"
    langtag = (
        r"%s(%s%s)?(%s%s)?(%s%s)*(%s%s)*(%s%s)?"
        % (language, delimiter, script, delimiter, region, delimiter, variant,
           delimiter, extension, delimiter, privateuse)
    )
    regex = r"(^%s$)|(^%s$)|(^%s$)" % (privateuse, grandfathered, langtag)
    return re.search(regex, value) is not None


# ---------------------------------------------------------------------------
# date / time
# ---------------------------------------------------------------------------

_ISO8601 = re.compile(
    r"^([\+-]?\d{4}(?!\d{2}\b))((-?)((0[1-9]|1[0-2])(\3([12]\d|0[1-9]|3[01]))?|W(0[1-9]|[1-4]\d|5[0-3])(-?[1-7])?|(00[1-9]|0[1-9]\d|[12]\d{2}|3([0-5]\d|6[0-6])))([T\s]((([01]\d|2[0-3])((:?)[0-5]\d)?|24:?00)([\.,]\d+(?!:))?)?(\17[0-5]\d([\.,]\d+)?)?([zZ]|([\+-])([01]\d|2[0-3]):?([0-5]\d)?)?)?)?$"
)
_ISO8601_STRICT = re.compile(
    r"^([\+-]?\d{4}(?!\d{2}\b))((-?)((0[1-9]|1[0-2])(\3([12]\d|0[1-9]|3[01]))?|W(0[1-9]|[1-4]\d|5[0-3])(-?[1-7])?|(00[1-9]|0[1-9]\d|[12]\d{2}|3([0-5]\d|6[0-6])))([T]((([01]\d|2[0-3])((:?)[0-5]\d)?|24:?00)([\.,]\d+(?!:))?)?(\17[0-5]\d([\.,]\d+)?)?([zZ]|([\+-])([01]\d|2[0-3]):?([0-5]\d)?)?)?)?$"
)


def _iso8601_valid_date(value):
    ordinal = re.match(r"^(\d{4})-?(\d{3})([ T]{1}\.*|$)", value)
    if ordinal:
        year = int(ordinal.group(1))
        day = int(ordinal.group(2))
        leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
        return day <= (366 if leap else 365)
    m = re.match(r"(\d{4})-?(\d{0,2})-?(\d*)", value)
    year = int(m.group(1))
    month = int(m.group(2)) if m.group(2) else 0
    day = int(m.group(3)) if m.group(3) else 0
    if month and day:
        import datetime

        try:
            datetime.date(year, month, day)
            return True
        except ValueError:
            return False
    return True


def isISO8601(value, options=None, **kwargs):
    _assert_string(value)
    o = _opts(options, kwargs, {})
    regex = _ISO8601_STRICT if o.get("strictSeparator") else _ISO8601
    check = regex.match(value) is not None
    if check and o.get("strict"):
        return _iso8601_valid_date(value)
    return check


_RFC3339 = re.compile(
    r"^[0-9]{4}-(0[1-9]|1[0-2])-([12]\d|0[1-9]|3[01])"
    r"[ tT]([01][0-9]|2[0-3]):[0-5][0-9]:([0-5][0-9]|60)(\.[0-9]+)?"
    r"([zZ]|[-+]([01][0-9]|2[0-3]):[0-5][0-9])$"
)


def isRFC3339(value):
    _assert_string(value)
    return _RFC3339.match(value) is not None


_TIME_FORMATS = {
    "hour24": {
        "default": r"^([01]?[0-9]|2[0-3]):([0-5][0-9])$",
        "withSeconds": r"^([01]?[0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])$",
        "withOptionalSeconds": r"^([01]?[0-9]|2[0-3]):([0-5][0-9])(?::([0-5][0-9]))?$",
    },
    "hour12": {
        "default": r"^(0?[1-9]|1[0-2]):([0-5][0-9]) (A|P)M$",
        "withSeconds": r"^(0?[1-9]|1[0-2]):([0-5][0-9]):([0-5][0-9]) (A|P)M$",
        "withOptionalSeconds": r"^(0?[1-9]|1[0-2]):([0-5][0-9])(?::([0-5][0-9]))? (A|P)M$",
    },
}


def isTime(value, options=None, **kwargs):
    o = _opts(options, kwargs, {"hourFormat": "hour24", "mode": "default"})
    if not isinstance(value, str):
        return False
    return re.match(_TIME_FORMATS[o["hourFormat"]][o["mode"]], value) is not None


_DATE_DEFAULTS = {"format": "YYYY/MM/DD", "delimiters": ["/", "-"], "strictMode": False}


def isDate(value, options=None, **kwargs):
    import datetime

    if isinstance(options, str):
        o = _merge({"format": options}, _DATE_DEFAULTS)
    else:
        o = _opts(options, kwargs, _DATE_DEFAULTS)
    fmt = o["format"]
    if isinstance(value, str) and re.match(
        r"(^(y{4}|y{2})[.\/-](m{1,2})[.\/-](d{1,2})$)"
        r"|(^(m{1,2})[.\/-](d{1,2})[.\/-]((y{4}|y{2})$))"
        r"|(^(d{1,2})[.\/-](m{1,2})[.\/-]((y{4}|y{2})$))",
        fmt, re.I,
    ):
        if o["strictMode"] and len(value) != len(fmt):
            return False
        fmt_delim = next((d for d in o["delimiters"] if d in fmt), None)
        date_delim = fmt_delim if o["strictMode"] else next((d for d in o["delimiters"] if d in value), None)
        if not date_delim:
            return False
        date_parts = value.split(date_delim)
        fmt_parts = fmt.lower().split(fmt_delim)
        obj = {}
        for i in range(max(len(date_parts), len(fmt_parts))):
            dw = date_parts[i] if i < len(date_parts) else None
            fw = fmt_parts[i] if i < len(fmt_parts) else None
            if not dw or not fw or len(dw) != len(fw):
                return False
            obj[fw[0]] = dw
        full_year = obj["y"]
        if full_year.startswith("-"):
            return False
        if len(obj["y"]) == 2:
            try:
                py = int(obj["y"])
            except ValueError:
                return False
            current = datetime.date.today().year % 100
            full_year = ("20" if py < current else "19") + obj["y"]
        month = obj["m"] if len(obj["m"]) == 2 else "0" + obj["m"]
        day = obj["d"] if len(obj["d"]) == 2 else "0" + obj["d"]
        try:
            return datetime.date(int(full_year), int(month), int(day)).day == int(obj["d"])
        except ValueError:
            return False
    return False


def isAfter(value, options=None, **kwargs):
    import datetime

    comparison = options.get("comparisonDate") if isinstance(options, dict) else options
    comparison = comparison or kwargs.get("comparisonDate") or datetime.datetime.now().isoformat()
    a = toDate(value)
    b = toDate(comparison)
    return bool(a and b and a > b)


def isBefore(value, options=None, **kwargs):
    import datetime

    comparison = options.get("comparisonDate") if isinstance(options, dict) else options
    comparison = comparison or kwargs.get("comparisonDate") or datetime.datetime.now().isoformat()
    a = toDate(value)
    b = toDate(comparison)
    return bool(a and b and a < b)


# ---------------------------------------------------------------------------
# ISO code sets
# ---------------------------------------------------------------------------


def isISO31661Alpha2(value):
    _assert_string(value)
    return value in _data.ISO_31661_ALPHA2


def isISO31661Alpha3(value):
    _assert_string(value)
    return value in _data.ISO_31661_ALPHA3


def isISO31661Numeric(value):
    _assert_string(value)
    return value in _data.ISO_31661_NUMERIC


def isISO4217(value):
    _assert_string(value)
    return value.upper() in _data.ISO_4217


def isISO6391(value):
    _assert_string(value)
    return value in _data.ISO_6391


def isISO15924(value):
    _assert_string(value)
    return value in _data.ISO_15924


_ISO6346 = re.compile(r"^[A-Z]{3}(U|J|Z)[0-9]{6}[0-9]$")


def isISO6346(value):
    _assert_string(value)
    value = value.upper()
    if not _ISO6346.match(value):
        return False
    total = 0
    for i in range(10):
        ch = value[i]
        if ch.isdigit():
            n = int(ch)
        else:
            n = ord(ch) - 55
            n += n // 11
        total += n * (2 ** i)
    check = total % 11 % 10
    return check == int(value[10])


def isFreightContainerID(value):
    return isISO6346(value)


# ---------------------------------------------------------------------------
# sanitizers / converters
# ---------------------------------------------------------------------------


def blacklist(value, chars):
    _assert_string(value)
    return re.sub("[%s]+" % chars, "", value)


def whitelist(value, chars):
    _assert_string(value)
    return re.sub("[^%s]+" % chars, "", value)


def stripLow(value, keep_new_lines=False):
    _assert_string(value)
    chars = r"\x00-\x09\x0B\x0C\x0E-\x1F\x7F" if keep_new_lines else r"\x00-\x1F\x7F"
    return blacklist(value, chars)


def ltrim(value, chars=None):
    _assert_string(value)
    if chars:
        return re.sub("^[%s]+" % _re_escape_class(chars), "", value)
    return re.sub(r"^\s+", "", value)


def rtrim(value, chars=None):
    _assert_string(value)
    if chars:
        return re.sub("[%s]+$" % _re_escape_class(chars), "", value)
    return re.sub(r"\s+$", "", value)


def trim(value, chars=None):
    return rtrim(ltrim(value, chars), chars)


def escape(value):
    _assert_string(value)
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("/", "&#x2F;")
        .replace("\\", "&#x5C;")
        .replace("`", "&#96;")
    )


def unescape(value):
    _assert_string(value)
    return (
        value.replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#x2F;", "/")
        .replace("&#x5C;", "\\")
        .replace("&#96;", "`")
        .replace("&amp;", "&")
    )


def toBoolean(value, strict=False):
    _assert_string(value)
    if strict:
        return value == "1" or re.match(r"^true$", value, re.I) is not None
    return value != "0" and re.match(r"^false$", value, re.I) is None and value != ""


def toInt(value, radix=10):
    _assert_string(value)
    return _parse_int(value, radix or 10)


def toFloat(value):
    if not isFloat(value):
        return math.nan
    return _parse_float(value)


def toDate(value):
    _assert_string(value)
    import datetime

    text = value.strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.datetime.fromisoformat(candidate)
        except ValueError:
            pass
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None


def toString(value):
    if isinstance(value, dict) or isinstance(value, list):
        return str(value)
    if value is None:
        return ""
    return str(value)


def normalizeEmail(value, options=None, **kwargs):
    """Reduced port: local-part lowercasing + gmail dot/subaddress handling."""
    _assert_string(value)
    o = _opts(options, kwargs, {
        "all_lowercase": True, "gmail_lowercase": True, "gmail_remove_dots": True,
        "gmail_remove_subaddress": True, "gmail_convert_googlemaildotcom": True,
    })
    parts = value.split("@")
    if len(parts) < 2:
        return False
    domain = parts.pop().lower()
    user = "@".join(parts)
    if domain in ("gmail.com", "googlemail.com"):
        if o["gmail_remove_subaddress"]:
            user = user.split("+")[0]
        if o["gmail_remove_dots"]:
            user = user.replace(".", "")
        if o["gmail_lowercase"]:
            user = user.lower()
        if o["gmail_convert_googlemaildotcom"]:
            domain = "gmail.com"
        if not user:
            return False
    elif o["all_lowercase"]:
        user = user.lower()
    return f"{user}@{domain}"


# ---------------------------------------------------------------------------
# namespace object (parity with validator.js default export)
# ---------------------------------------------------------------------------

_NAMES = [
    name for name, obj in list(globals().items())
    if callable(obj) and (name[:2] == "is" or name in {
        "contains", "equals", "matches", "blacklist", "whitelist", "stripLow",
        "ltrim", "rtrim", "trim", "escape", "unescape", "toBoolean", "toInt",
        "toFloat", "toDate", "toString", "normalizeEmail",
    })
]

__all__ = ["version", *sorted(_NAMES)]
