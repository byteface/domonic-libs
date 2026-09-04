# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/identifier.js.
# Preserve the upstream licence when redistributing.
"""Reserved words, keyword lists, and the ``isIdentifierStart`` /
``isIdentifierChar`` character predicates.

The two ``nonASCIIidentifier*`` regexes are built exactly as upstream does --
``new RegExp("[" + chars + "]")`` -- so they exercise ``domonic.javascript``'s
``RegExp`` on a large character class of ``\\uXXXX`` escapes and ranges. The
astral lookups run through ``String.fromCharCode`` the same way.
"""

from __future__ import annotations

from domonic.javascript import RegExp, String

from ._generated import (
    astralIdentifierCodes,
    astralIdentifierStartCodes,
    nonASCIIidentifierChars,
    nonASCIIidentifierStartChars,
)

# Reserved word lists for various dialects of the language

reservedWords = {
    3: "abstract boolean byte char class double enum export extends final float goto implements import int interface long native package private protected public short static super synchronized throws transient volatile",
    5: "class enum extends super const export import",
    6: "enum",
    "strict": "implements interface let package private protected public static yield",
    "strictBind": "eval arguments",
}

# And the keywords

_ecma5AndLessKeywords = "break case catch continue debugger default do else finally for function if return switch throw try var while with null true false instanceof typeof void delete new in this"

keywords = {
    5: _ecma5AndLessKeywords,
    "5module": _ecma5AndLessKeywords + " export import",
    6: _ecma5AndLessKeywords + " const class extends export import super",
}

keywordRelationalOperator = RegExp(r"^in(stanceof)?$")

# ## Character categories

nonASCIIidentifierStart = RegExp("[" + nonASCIIidentifierStartChars + "]")
nonASCIIidentifier = RegExp("[" + nonASCIIidentifierStartChars + nonASCIIidentifierChars + "]")


def _isInAstralSet(code, s):
    """Linear scan of a run-length/offset table (rare path, per upstream)."""
    pos = 0x10000
    for i in range(0, len(s), 2):
        pos += s[i]
        if pos > code:
            return False
        pos += s[i + 1]
        if pos >= code:
            return True
    return False


def isIdentifierStart(code, astral=None):
    """Whether ``code`` (a code point) may begin an identifier."""
    if code < 65:
        return code == 36
    if code < 91:
        return True
    if code < 97:
        return code == 95
    if code < 123:
        return True
    if code <= 0xFFFF:
        return code >= 0xAA and bool(nonASCIIidentifierStart.test(String.fromCharCode(code)))
    if astral is False:
        return False
    return _isInAstralSet(code, astralIdentifierStartCodes)


def isIdentifierChar(code, astral=None):
    """Whether ``code`` (a code point) may continue an identifier."""
    if code < 48:
        return code == 36
    if code < 58:
        return True
    if code < 65:
        return False
    if code < 91:
        return True
    if code < 97:
        return code == 95
    if code < 123:
        return True
    if code <= 0xFFFF:
        return code >= 0xAA and bool(nonASCIIidentifier.test(String.fromCharCode(code)))
    if astral is False:
        return False
    return _isInAstralSet(code, astralIdentifierStartCodes) or _isInAstralSet(code, astralIdentifierCodes)
