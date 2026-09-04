# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/util.js.
# Preserve the upstream licence when redistributing.
"""Small shared helpers.

``wordsRegexp`` compiles a space-separated word list into an anchored
alternation and caches it -- the same regex the tokenizer uses for keyword
matching. ``codePointToString`` is UTF-16 surrogate-pair encoding, which is
where a code-point-based Python string model tends to diverge from JS.
"""

from __future__ import annotations

from domonic.javascript import RegExp, String


def hasOwn(obj, prop):
    if isinstance(obj, dict):
        return prop in obj
    return hasattr(obj, prop)


def isArray(obj):
    return isinstance(obj, (list, tuple))


_regexpCache = {}


def wordsRegexp(words):
    """``new RegExp("^(?:" + words.replace(/ /g, "|") + ")$")``, memoised."""
    if words not in _regexpCache:
        _regexpCache[words] = RegExp("^(?:" + String(words).replace(RegExp(" ", "g"), "|") + ")$")
    return _regexpCache[words]


def codePointToString(code):
    # UTF-16 Decoding. domonic 1.6's String models code units, so
    # fromCharCode of a surrogate pair recombines into the astral character.
    code = int(code)
    if code <= 0xFFFF:
        return String.fromCharCode(code)
    code -= 0x10000
    return String.fromCharCode((code >> 10) + 0xD800, (code & 1023) + 0xDC00)


# /[\uD800-\uDFFF]/u
loneSurrogate = RegExp("[\\uD800-\\uDFFF]", "u")
