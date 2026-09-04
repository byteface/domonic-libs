# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/regexp.js.
# Preserve the upstream licence when redistributing.
"""``RegExpValidationState`` and the ``regexp_*`` grammar walker -- acorn's
character-by-character validator for regex literals against the ECMAScript
regex grammar.

This is the densest ``domonic.javascript`` probe in the port: ``at`` / ``nextIndex``
do surrogate-aware ``charCodeAt`` on the pattern String, the ``\\u`` / ``\\u{...}``
paths lean on hex parsing + ``codePointToString``, and ``\\p{...}`` runs the
Unicode-property word lists.
"""

from __future__ import annotations

from domonic.javascript import String

from .identifier import isIdentifierChar, isIdentifierStart
from .util import codePointToString, hasOwn
from .unicode_property_data import data as UNICODE_PROPERTY_VALUES


class BranchID:
    def __init__(self, parent, base=None):
        self.parent = parent
        self.base = base or self

    def separatedFrom(self, alt):
        self_ = self
        while self_:
            other = alt
            while other:
                if self_.base is other.base and self_ is not other:
                    return True
                other = other.parent
            self_ = self_.parent
        return False

    def sibling(self):
        return BranchID(self.parent, self.base)


class RegExpValidationState:
    def __init__(self, parser):
        self.parser = parser
        ev = parser.options["ecmaVersion"]
        self.validFlags = "gim" + ("uy" if ev >= 6 else "") + ("s" if ev >= 9 else "") + \
            ("d" if ev >= 13 else "") + ("v" if ev >= 15 else "")
        self.unicodeProperties = UNICODE_PROPERTY_VALUES[14 if ev >= 14 else ev]
        self.source = String("")
        self.flags = ""
        self.start = 0
        self.switchU = False
        self.switchV = False
        self.switchN = False
        self.pos = 0
        self.lastIntValue = 0
        self.lastStringValue = ""
        self.lastAssertionIsQuantifiable = False
        self.numCapturingParens = 0
        self.maxBackReference = 0
        self.groupNames = {}
        self.backReferenceNames = []
        self.branchID = None

    def reset(self, start, pattern, flags):
        unicodeSets = flags.find("v") != -1
        unicode = flags.find("u") != -1
        self.start = int(start)
        self.source = String(pattern)
        self.flags = flags
        ev = self.parser.options["ecmaVersion"]
        if unicodeSets and ev >= 15:
            self.switchU = self.switchV = self.switchN = True
        else:
            self.switchU = unicode and ev >= 6
            self.switchV = False
            self.switchN = unicode and ev >= 9

    def raise_(self, message):
        self.parser.raiseRecoverable(self.start, f"Invalid regular expression: /{self.source}/: {message}")

    def at(self, i, forceU=False):
        s = self.source
        length = s.length
        if i >= length:
            return -1
        c = s.charCodeAt(i)
        if not (forceU or self.switchU) or c <= 0xD7FF or c >= 0xE000 or i + 1 >= length:
            return c
        nxt = s.charCodeAt(i + 1)
        return (c << 10) + nxt - 0x35FDC00 if (0xDC00 <= nxt <= 0xDFFF) else c

    def nextIndex(self, i, forceU=False):
        s = self.source
        length = s.length
        if i >= length:
            return length
        c = s.charCodeAt(i)
        if not (forceU or self.switchU) or c <= 0xD7FF or c >= 0xE000 or i + 1 >= length:
            return i + 1
        nxt = s.charCodeAt(i + 1)
        if nxt < 0xDC00 or nxt > 0xDFFF:
            return i + 1
        return i + 2

    def current(self, forceU=False):
        return self.at(self.pos, forceU)

    def lookahead(self, forceU=False):
        return self.at(self.nextIndex(self.pos, forceU), forceU)

    def advance(self, forceU=False):
        self.pos = self.nextIndex(self.pos, forceU)

    def eat(self, ch, forceU=False):
        if self.current(forceU) == ch:
            self.advance(forceU)
            return True
        return False

    def eatChars(self, chs, forceU=False):
        pos = self.pos
        for ch in chs:
            current = self.at(pos, forceU)
            if current == -1 or current != ch:
                return False
            pos = self.nextIndex(pos, forceU)
        self.pos = pos
        return True


# -- character-class predicate helpers -------------------------------------

def _isSyntaxCharacter(ch):
    return (ch == 0x24 or 0x28 <= ch <= 0x2B or ch == 0x2E or ch == 0x3F
            or 0x5B <= ch <= 0x5E or 0x7B <= ch <= 0x7D)


def _isRegExpIdentifierStart(ch):
    return isIdentifierStart(ch, True) or ch == 0x24 or ch == 0x5F


def _isRegExpIdentifierPart(ch):
    return (isIdentifierChar(ch, True) or ch == 0x24 or ch == 0x5F
            or ch == 0x200C or ch == 0x200D)


def _isControlLetter(ch):
    return 0x41 <= ch <= 0x5A or 0x61 <= ch <= 0x7A


def _isRegularExpressionModifier(ch):
    return ch == 0x69 or ch == 0x6D or ch == 0x73


def _isCharacterClassEscape(ch):
    return ch in (0x64, 0x44, 0x73, 0x53, 0x77, 0x57)


def _isUnicodePropertyNameCharacter(ch):
    return _isControlLetter(ch) or ch == 0x5F


def _isDecimalDigit(ch):
    return 0x30 <= ch <= 0x39


def _isUnicodePropertyValueCharacter(ch):
    return _isUnicodePropertyNameCharacter(ch) or _isDecimalDigit(ch)


def _isHexDigit(ch):
    return 0x30 <= ch <= 0x39 or 0x41 <= ch <= 0x46 or 0x61 <= ch <= 0x66


def _hexToInt(ch):
    if 0x41 <= ch <= 0x46:
        return 10 + (ch - 0x41)
    if 0x61 <= ch <= 0x66:
        return 10 + (ch - 0x61)
    return ch - 0x30


def _isOctalDigit(ch):
    return 0x30 <= ch <= 0x37


def _isValidUnicode(ch):
    return 0 <= ch <= 0x10FFFF


def _isClassSetReservedDoublePunctuatorCharacter(ch):
    return (ch == 0x21 or 0x23 <= ch <= 0x26 or 0x2A <= ch <= 0x2C or ch == 0x2E
            or 0x3A <= ch <= 0x40 or ch == 0x5E or ch == 0x60 or ch == 0x7E)


def _isClassSetSyntaxCharacter(ch):
    return (ch == 0x28 or ch == 0x29 or ch == 0x2D or ch == 0x2F
            or 0x5B <= ch <= 0x5D or 0x7B <= ch <= 0x7D)


def _isClassSetReservedPunctuator(ch):
    return (ch == 0x21 or ch == 0x23 or ch == 0x25 or ch == 0x26 or ch == 0x2C
            or ch == 0x2D or 0x3A <= ch <= 0x3E or ch == 0x40 or ch == 0x60 or ch == 0x7E)


_CHARSET_NONE = 0
_CHARSET_OK = 1
_CHARSET_STRING = 2


class RegExpValidateMixin:
    def validateRegExpFlags(self, state):
        validFlags = state.validFlags
        flags = state.flags
        u = v = False
        for i in range(len(flags)):
            flag = flags[i]
            if validFlags.find(flag) == -1:
                self.raise_(state.start, "Invalid regular expression flag")
            if flags.find(flag, i + 1) > -1:
                self.raise_(state.start, "Duplicate regular expression flag")
            if flag == "u":
                u = True
            if flag == "v":
                v = True
        if self.options["ecmaVersion"] >= 15 and u and v:
            self.raise_(state.start, "Invalid regular expression flag")

    def validateRegExpPattern(self, state):
        self.regexp_pattern(state)
        if not state.switchN and self.options["ecmaVersion"] >= 9 and bool(state.groupNames):
            state.switchN = True
            self.regexp_pattern(state)

    def regexp_pattern(self, state):
        state.pos = 0
        state.lastIntValue = 0
        state.lastStringValue = ""
        state.lastAssertionIsQuantifiable = False
        state.numCapturingParens = 0
        state.maxBackReference = 0
        state.groupNames = {}
        state.backReferenceNames[:] = []
        state.branchID = None

        self.regexp_disjunction(state)

        if state.pos != state.source.length:
            if state.eat(0x29):
                state.raise_("Unmatched ')'")
            if state.eat(0x5D) or state.eat(0x7D):
                state.raise_("Lone quantifier brackets")
        if state.maxBackReference > state.numCapturingParens:
            state.raise_("Invalid escape")
        for name in state.backReferenceNames:
            if not state.groupNames.get(name):
                state.raise_("Invalid named capture referenced")

    def regexp_disjunction(self, state):
        trackDisjunction = self.options["ecmaVersion"] >= 16
        if trackDisjunction:
            state.branchID = BranchID(state.branchID, None)
        self.regexp_alternative(state)
        while state.eat(0x7C):
            if trackDisjunction:
                state.branchID = state.branchID.sibling()
            self.regexp_alternative(state)
        if trackDisjunction:
            state.branchID = state.branchID.parent

        if self.regexp_eatQuantifier(state, True):
            state.raise_("Nothing to repeat")
        if state.eat(0x7B):
            state.raise_("Lone quantifier brackets")

    def regexp_alternative(self, state):
        while state.pos < state.source.length and self.regexp_eatTerm(state):
            pass

    def regexp_eatTerm(self, state):
        if self.regexp_eatAssertion(state):
            if state.lastAssertionIsQuantifiable and self.regexp_eatQuantifier(state):
                if state.switchU:
                    state.raise_("Invalid quantifier")
            return True
        if self.regexp_eatAtom(state) if state.switchU else self.regexp_eatExtendedAtom(state):
            self.regexp_eatQuantifier(state)
            return True
        return False

    def regexp_eatAssertion(self, state):
        start = state.pos
        state.lastAssertionIsQuantifiable = False
        if state.eat(0x5E) or state.eat(0x24):
            return True
        if state.eat(0x5C):
            if state.eat(0x42) or state.eat(0x62):
                return True
            state.pos = start
        if state.eat(0x28) and state.eat(0x3F):
            lookbehind = False
            if self.options["ecmaVersion"] >= 9:
                lookbehind = state.eat(0x3C)
            if state.eat(0x3D) or state.eat(0x21):
                self.regexp_disjunction(state)
                if not state.eat(0x29):
                    state.raise_("Unterminated group")
                state.lastAssertionIsQuantifiable = not lookbehind
                return True
        state.pos = start
        return False

    def regexp_eatQuantifier(self, state, noError=False):
        if self.regexp_eatQuantifierPrefix(state, noError):
            state.eat(0x3F)
            return True
        return False

    def regexp_eatQuantifierPrefix(self, state, noError):
        return (state.eat(0x2A) or state.eat(0x2B) or state.eat(0x3F)
                or self.regexp_eatBracedQuantifier(state, noError))

    def regexp_eatBracedQuantifier(self, state, noError):
        start = state.pos
        if state.eat(0x7B):
            mn = 0
            mx = -1
            if self.regexp_eatDecimalDigits(state):
                mn = state.lastIntValue
                if state.eat(0x2C) and self.regexp_eatDecimalDigits(state):
                    mx = state.lastIntValue
                if state.eat(0x7D):
                    if mx != -1 and mx < mn and not noError:
                        state.raise_("numbers out of order in {} quantifier")
                    return True
            if state.switchU and not noError:
                state.raise_("Incomplete quantifier")
            state.pos = start
        return False

    def regexp_eatAtom(self, state):
        return (self.regexp_eatPatternCharacters(state)
                or state.eat(0x2E)
                or self.regexp_eatReverseSolidusAtomEscape(state)
                or self.regexp_eatCharacterClass(state)
                or self.regexp_eatUncapturingGroup(state)
                or self.regexp_eatCapturingGroup(state))

    def regexp_eatReverseSolidusAtomEscape(self, state):
        start = state.pos
        if state.eat(0x5C):
            if self.regexp_eatAtomEscape(state):
                return True
            state.pos = start
        return False

    def regexp_eatUncapturingGroup(self, state):
        start = state.pos
        if state.eat(0x28):
            if state.eat(0x3F):
                if self.options["ecmaVersion"] >= 16:
                    addModifiers = self.regexp_eatModifiers(state)
                    hasHyphen = state.eat(0x2D)
                    if addModifiers or hasHyphen:
                        for i in range(len(addModifiers)):
                            modifier = addModifiers[i]
                            if addModifiers.find(modifier, i + 1) > -1:
                                state.raise_("Duplicate regular expression modifiers")
                        if hasHyphen:
                            removeModifiers = self.regexp_eatModifiers(state)
                            if not addModifiers and not removeModifiers and state.current() == 0x3A:
                                state.raise_("Invalid regular expression modifiers")
                            for i in range(len(removeModifiers)):
                                modifier = removeModifiers[i]
                                if removeModifiers.find(modifier, i + 1) > -1 or addModifiers.find(modifier) > -1:
                                    state.raise_("Duplicate regular expression modifiers")
                if state.eat(0x3A):
                    self.regexp_disjunction(state)
                    if state.eat(0x29):
                        return True
                    state.raise_("Unterminated group")
            state.pos = start
        return False

    def regexp_eatCapturingGroup(self, state):
        if state.eat(0x28):
            if self.options["ecmaVersion"] >= 9:
                self.regexp_groupSpecifier(state)
            elif state.current() == 0x3F:
                state.raise_("Invalid group")
            self.regexp_disjunction(state)
            if state.eat(0x29):
                state.numCapturingParens += 1
                return True
            state.raise_("Unterminated group")
        return False

    def regexp_eatModifiers(self, state):
        modifiers = ""
        while True:
            ch = state.current()
            if ch == -1 or not _isRegularExpressionModifier(ch):
                break
            modifiers += codePointToString(ch)
            state.advance()
        return modifiers

    def regexp_eatExtendedAtom(self, state):
        return (state.eat(0x2E)
                or self.regexp_eatReverseSolidusAtomEscape(state)
                or self.regexp_eatCharacterClass(state)
                or self.regexp_eatUncapturingGroup(state)
                or self.regexp_eatCapturingGroup(state)
                or self.regexp_eatInvalidBracedQuantifier(state)
                or self.regexp_eatExtendedPatternCharacter(state))

    def regexp_eatInvalidBracedQuantifier(self, state):
        if self.regexp_eatBracedQuantifier(state, True):
            state.raise_("Nothing to repeat")
        return False

    def regexp_eatSyntaxCharacter(self, state):
        ch = state.current()
        if _isSyntaxCharacter(ch):
            state.lastIntValue = ch
            state.advance()
            return True
        return False

    def regexp_eatPatternCharacters(self, state):
        start = state.pos
        while True:
            ch = state.current()
            if ch == -1 or _isSyntaxCharacter(ch):
                break
            state.advance()
        return state.pos != start

    def regexp_eatExtendedPatternCharacter(self, state):
        ch = state.current()
        if (ch != -1 and ch != 0x24 and not (0x28 <= ch <= 0x2B) and ch != 0x2E
                and ch != 0x3F and ch != 0x5B and ch != 0x5E and ch != 0x7C):
            state.advance()
            return True
        return False

    def regexp_groupSpecifier(self, state):
        if state.eat(0x3F):
            if not self.regexp_eatGroupName(state):
                state.raise_("Invalid group")
            trackDisjunction = self.options["ecmaVersion"] >= 16
            known = state.groupNames.get(state.lastStringValue)
            if known:
                if trackDisjunction:
                    for altID in known:
                        if not altID.separatedFrom(state.branchID):
                            state.raise_("Duplicate capture group name")
                else:
                    state.raise_("Duplicate capture group name")
            if trackDisjunction:
                if not known:
                    known = state.groupNames[state.lastStringValue] = []
                known.append(state.branchID)
            else:
                state.groupNames[state.lastStringValue] = True

    def regexp_eatGroupName(self, state):
        state.lastStringValue = ""
        if state.eat(0x3C):
            if self.regexp_eatRegExpIdentifierName(state) and state.eat(0x3E):
                return True
            state.raise_("Invalid capture group name")
        return False

    def regexp_eatRegExpIdentifierName(self, state):
        state.lastStringValue = ""
        if self.regexp_eatRegExpIdentifierStart(state):
            state.lastStringValue += codePointToString(state.lastIntValue)
            while self.regexp_eatRegExpIdentifierPart(state):
                state.lastStringValue += codePointToString(state.lastIntValue)
            return True
        return False

    def regexp_eatRegExpIdentifierStart(self, state):
        start = state.pos
        forceU = self.options["ecmaVersion"] >= 11
        ch = state.current(forceU)
        state.advance(forceU)
        if ch == 0x5C and self.regexp_eatRegExpUnicodeEscapeSequence(state, forceU):
            ch = state.lastIntValue
        if _isRegExpIdentifierStart(ch):
            state.lastIntValue = ch
            return True
        state.pos = start
        return False

    def regexp_eatRegExpIdentifierPart(self, state):
        start = state.pos
        forceU = self.options["ecmaVersion"] >= 11
        ch = state.current(forceU)
        state.advance(forceU)
        if ch == 0x5C and self.regexp_eatRegExpUnicodeEscapeSequence(state, forceU):
            ch = state.lastIntValue
        if _isRegExpIdentifierPart(ch):
            state.lastIntValue = ch
            return True
        state.pos = start
        return False

    def regexp_eatAtomEscape(self, state):
        if (self.regexp_eatBackReference(state)
                or self.regexp_eatCharacterClassEscape(state)
                or self.regexp_eatCharacterEscape(state)
                or (state.switchN and self.regexp_eatKGroupName(state))):
            return True
        if state.switchU:
            if state.current() == 0x63:
                state.raise_("Invalid unicode escape")
            state.raise_("Invalid escape")
        return False

    def regexp_eatBackReference(self, state):
        start = state.pos
        if self.regexp_eatDecimalEscape(state):
            n = state.lastIntValue
            if state.switchU:
                if n > state.maxBackReference:
                    state.maxBackReference = n
                return True
            if n <= state.numCapturingParens:
                return True
            state.pos = start
        return False

    def regexp_eatKGroupName(self, state):
        if state.eat(0x6B):
            if self.regexp_eatGroupName(state):
                state.backReferenceNames.append(state.lastStringValue)
                return True
            state.raise_("Invalid named reference")
        return False

    def regexp_eatCharacterEscape(self, state):
        return (self.regexp_eatControlEscape(state)
                or self.regexp_eatCControlLetter(state)
                or self.regexp_eatZero(state)
                or self.regexp_eatHexEscapeSequence(state)
                or self.regexp_eatRegExpUnicodeEscapeSequence(state, False)
                or (not state.switchU and self.regexp_eatLegacyOctalEscapeSequence(state))
                or self.regexp_eatIdentityEscape(state))

    def regexp_eatCControlLetter(self, state):
        start = state.pos
        if state.eat(0x63):
            if self.regexp_eatControlLetter(state):
                return True
            state.pos = start
        return False

    def regexp_eatZero(self, state):
        if state.current() == 0x30 and not _isDecimalDigit(state.lookahead()):
            state.lastIntValue = 0
            state.advance()
            return True
        return False

    def regexp_eatControlEscape(self, state):
        ch = state.current()
        mapping = {0x74: 0x09, 0x6E: 0x0A, 0x76: 0x0B, 0x66: 0x0C, 0x72: 0x0D}
        if ch in mapping:
            state.lastIntValue = mapping[ch]
            state.advance()
            return True
        return False

    def regexp_eatControlLetter(self, state):
        ch = state.current()
        if _isControlLetter(ch):
            state.lastIntValue = ch % 0x20
            state.advance()
            return True
        return False

    def regexp_eatRegExpUnicodeEscapeSequence(self, state, forceU=False):
        start = state.pos
        switchU = forceU or state.switchU
        if state.eat(0x75):
            if self.regexp_eatFixedHexDigits(state, 4):
                lead = state.lastIntValue
                if switchU and 0xD800 <= lead <= 0xDBFF:
                    leadSurrogateEnd = state.pos
                    if state.eat(0x5C) and state.eat(0x75) and self.regexp_eatFixedHexDigits(state, 4):
                        trail = state.lastIntValue
                        if 0xDC00 <= trail <= 0xDFFF:
                            state.lastIntValue = (lead - 0xD800) * 0x400 + (trail - 0xDC00) + 0x10000
                            return True
                    state.pos = leadSurrogateEnd
                    state.lastIntValue = lead
                return True
            if (switchU and state.eat(0x7B) and self.regexp_eatHexDigits(state)
                    and state.eat(0x7D) and _isValidUnicode(state.lastIntValue)):
                return True
            if switchU:
                state.raise_("Invalid unicode escape")
            state.pos = start
        return False

    def regexp_eatIdentityEscape(self, state):
        if state.switchU:
            if self.regexp_eatSyntaxCharacter(state):
                return True
            if state.eat(0x2F):
                state.lastIntValue = 0x2F
                return True
            return False
        ch = state.current()
        if ch != 0x63 and (not state.switchN or ch != 0x6B):
            state.lastIntValue = ch
            state.advance()
            return True
        return False

    def regexp_eatDecimalEscape(self, state):
        state.lastIntValue = 0
        ch = state.current()
        if 0x31 <= ch <= 0x39:
            while True:
                state.lastIntValue = 10 * state.lastIntValue + (ch - 0x30)
                state.advance()
                ch = state.current()
                if not (0x30 <= ch <= 0x39):
                    break
            return True
        return False

    def regexp_eatCharacterClassEscape(self, state):
        ch = state.current()
        if _isCharacterClassEscape(ch):
            state.lastIntValue = -1
            state.advance()
            return _CHARSET_OK
        negate = False
        if state.switchU and self.options["ecmaVersion"] >= 9:
            negate = ch == 0x50
            if negate or ch == 0x70:
                state.lastIntValue = -1
                state.advance()
                result = None
                if state.eat(0x7B):
                    result = self.regexp_eatUnicodePropertyValueExpression(state)
                    if result and state.eat(0x7D):
                        if negate and result == _CHARSET_STRING:
                            state.raise_("Invalid property name")
                        return result
                state.raise_("Invalid property name")
        return _CHARSET_NONE

    def regexp_eatUnicodePropertyValueExpression(self, state):
        start = state.pos
        if self.regexp_eatUnicodePropertyName(state) and state.eat(0x3D):
            name = state.lastStringValue
            if self.regexp_eatUnicodePropertyValue(state):
                value = state.lastStringValue
                self.regexp_validateUnicodePropertyNameAndValue(state, name, value)
                return _CHARSET_OK
        state.pos = start
        if self.regexp_eatLoneUnicodePropertyNameOrValue(state):
            nameOrValue = state.lastStringValue
            return self.regexp_validateUnicodePropertyNameOrValue(state, nameOrValue)
        return _CHARSET_NONE

    def regexp_validateUnicodePropertyNameAndValue(self, state, name, value):
        if not hasOwn(state.unicodeProperties["nonBinary"], name):
            state.raise_("Invalid property name")
        if not state.unicodeProperties["nonBinary"][name].test(value):
            state.raise_("Invalid property value")

    def regexp_validateUnicodePropertyNameOrValue(self, state, nameOrValue):
        if bool(state.unicodeProperties["binary"].test(nameOrValue)):
            return _CHARSET_OK
        if state.switchV and bool(state.unicodeProperties["binaryOfStrings"].test(nameOrValue)):
            return _CHARSET_STRING
        state.raise_("Invalid property name")

    def regexp_eatUnicodePropertyName(self, state):
        state.lastStringValue = ""
        while True:
            ch = state.current()
            if not _isUnicodePropertyNameCharacter(ch):
                break
            state.lastStringValue += codePointToString(ch)
            state.advance()
        return state.lastStringValue != ""

    def regexp_eatUnicodePropertyValue(self, state):
        state.lastStringValue = ""
        while True:
            ch = state.current()
            if not _isUnicodePropertyValueCharacter(ch):
                break
            state.lastStringValue += codePointToString(ch)
            state.advance()
        return state.lastStringValue != ""

    def regexp_eatLoneUnicodePropertyNameOrValue(self, state):
        return self.regexp_eatUnicodePropertyValue(state)

    def regexp_eatCharacterClass(self, state):
        if state.eat(0x5B):
            negate = state.eat(0x5E)
            result = self.regexp_classContents(state)
            if not state.eat(0x5D):
                state.raise_("Unterminated character class")
            if negate and result == _CHARSET_STRING:
                state.raise_("Negated character class may contain strings")
            return True
        return False

    def regexp_classContents(self, state):
        if state.current() == 0x5D:
            return _CHARSET_OK
        if state.switchV:
            return self.regexp_classSetExpression(state)
        self.regexp_nonEmptyClassRanges(state)
        return _CHARSET_OK

    def regexp_nonEmptyClassRanges(self, state):
        while self.regexp_eatClassAtom(state):
            left = state.lastIntValue
            if state.eat(0x2D) and self.regexp_eatClassAtom(state):
                right = state.lastIntValue
                if state.switchU and (left == -1 or right == -1):
                    state.raise_("Invalid character class")
                if left != -1 and right != -1 and left > right:
                    state.raise_("Range out of order in character class")

    def regexp_eatClassAtom(self, state):
        start = state.pos
        if state.eat(0x5C):
            if self.regexp_eatClassEscape(state):
                return True
            if state.switchU:
                ch = state.current()
                if ch == 0x63 or _isOctalDigit(ch):
                    state.raise_("Invalid class escape")
                state.raise_("Invalid escape")
            state.pos = start
        ch = state.current()
        if ch != 0x5D:
            state.lastIntValue = ch
            state.advance()
            return True
        return False

    def regexp_eatClassEscape(self, state):
        start = state.pos
        if state.eat(0x62):
            state.lastIntValue = 0x08
            return True
        if state.switchU and state.eat(0x2D):
            state.lastIntValue = 0x2D
            return True
        if not state.switchU and state.eat(0x63):
            if self.regexp_eatClassControlLetter(state):
                return True
            state.pos = start
        return (self.regexp_eatCharacterClassEscape(state)
                or self.regexp_eatCharacterEscape(state))

    def regexp_classSetExpression(self, state):
        result = _CHARSET_OK
        if self.regexp_eatClassSetRange(state):
            pass
        else:
            subResult = self.regexp_eatClassSetOperand(state)
            if subResult:
                if subResult == _CHARSET_STRING:
                    result = _CHARSET_STRING
                start = state.pos
                while state.eatChars([0x26, 0x26]):
                    if state.current() != 0x26 and (sub := self.regexp_eatClassSetOperand(state)):
                        if sub != _CHARSET_STRING:
                            result = _CHARSET_OK
                        continue
                    state.raise_("Invalid character in character class")
                if start != state.pos:
                    return result
                while state.eatChars([0x2D, 0x2D]):
                    if self.regexp_eatClassSetOperand(state):
                        continue
                    state.raise_("Invalid character in character class")
                if start != state.pos:
                    return result
            else:
                state.raise_("Invalid character in character class")
        while True:
            if self.regexp_eatClassSetRange(state):
                continue
            subResult = self.regexp_eatClassSetOperand(state)
            if not subResult:
                return result
            if subResult == _CHARSET_STRING:
                result = _CHARSET_STRING

    def regexp_eatClassSetRange(self, state):
        start = state.pos
        if self.regexp_eatClassSetCharacter(state):
            left = state.lastIntValue
            if state.eat(0x2D) and self.regexp_eatClassSetCharacter(state):
                right = state.lastIntValue
                if left != -1 and right != -1 and left > right:
                    state.raise_("Range out of order in character class")
                return True
            state.pos = start
        return False

    def regexp_eatClassSetOperand(self, state):
        if self.regexp_eatClassSetCharacter(state):
            return _CHARSET_OK
        return self.regexp_eatClassStringDisjunction(state) or self.regexp_eatNestedClass(state)

    def regexp_eatNestedClass(self, state):
        start = state.pos
        if state.eat(0x5B):
            negate = state.eat(0x5E)
            result = self.regexp_classContents(state)
            if state.eat(0x5D):
                if negate and result == _CHARSET_STRING:
                    state.raise_("Negated character class may contain strings")
                return result
            state.pos = start
        if state.eat(0x5C):
            result = self.regexp_eatCharacterClassEscape(state)
            if result:
                return result
            state.pos = start
        return None

    def regexp_eatClassStringDisjunction(self, state):
        start = state.pos
        if state.eatChars([0x5C, 0x71]):
            if state.eat(0x7B):
                result = self.regexp_classStringDisjunctionContents(state)
                if state.eat(0x7D):
                    return result
            else:
                state.raise_("Invalid escape")
            state.pos = start
        return None

    def regexp_classStringDisjunctionContents(self, state):
        result = self.regexp_classString(state)
        while state.eat(0x7C):
            if self.regexp_classString(state) == _CHARSET_STRING:
                result = _CHARSET_STRING
        return result

    def regexp_classString(self, state):
        count = 0
        while self.regexp_eatClassSetCharacter(state):
            count += 1
        return _CHARSET_OK if count == 1 else _CHARSET_STRING

    def regexp_eatClassSetCharacter(self, state):
        start = state.pos
        if state.eat(0x5C):
            if self.regexp_eatCharacterEscape(state) or self.regexp_eatClassSetReservedPunctuator(state):
                return True
            if state.eat(0x62):
                state.lastIntValue = 0x08
                return True
            state.pos = start
            return False
        ch = state.current()
        if ch < 0 or (ch == state.lookahead() and _isClassSetReservedDoublePunctuatorCharacter(ch)):
            return False
        if _isClassSetSyntaxCharacter(ch):
            return False
        state.advance()
        state.lastIntValue = ch
        return True

    def regexp_eatClassSetReservedPunctuator(self, state):
        ch = state.current()
        if _isClassSetReservedPunctuator(ch):
            state.lastIntValue = ch
            state.advance()
            return True
        return False

    def regexp_eatClassControlLetter(self, state):
        ch = state.current()
        if _isDecimalDigit(ch) or ch == 0x5F:
            state.lastIntValue = ch % 0x20
            state.advance()
            return True
        return False

    def regexp_eatHexEscapeSequence(self, state):
        start = state.pos
        if state.eat(0x78):
            if self.regexp_eatFixedHexDigits(state, 2):
                return True
            if state.switchU:
                state.raise_("Invalid escape")
            state.pos = start
        return False

    def regexp_eatDecimalDigits(self, state):
        start = state.pos
        state.lastIntValue = 0
        while True:
            ch = state.current()
            if not _isDecimalDigit(ch):
                break
            state.lastIntValue = 10 * state.lastIntValue + (ch - 0x30)
            state.advance()
        return state.pos != start

    def regexp_eatHexDigits(self, state):
        start = state.pos
        state.lastIntValue = 0
        while True:
            ch = state.current()
            if not _isHexDigit(ch):
                break
            state.lastIntValue = 16 * state.lastIntValue + _hexToInt(ch)
            state.advance()
        return state.pos != start

    def regexp_eatLegacyOctalEscapeSequence(self, state):
        if self.regexp_eatOctalDigit(state):
            n1 = state.lastIntValue
            if self.regexp_eatOctalDigit(state):
                n2 = state.lastIntValue
                if n1 <= 3 and self.regexp_eatOctalDigit(state):
                    state.lastIntValue = n1 * 64 + n2 * 8 + state.lastIntValue
                else:
                    state.lastIntValue = n1 * 8 + n2
            else:
                state.lastIntValue = n1
            return True
        return False

    def regexp_eatOctalDigit(self, state):
        ch = state.current()
        if _isOctalDigit(ch):
            state.lastIntValue = ch - 0x30
            state.advance()
            return True
        state.lastIntValue = 0
        return False

    def regexp_eatFixedHexDigits(self, state, length):
        start = state.pos
        state.lastIntValue = 0
        for _ in range(length):
            ch = state.current()
            if not _isHexDigit(ch):
                state.pos = start
                return False
            state.lastIntValue = 16 * state.lastIntValue + _hexToInt(ch)
            state.advance()
        return True
