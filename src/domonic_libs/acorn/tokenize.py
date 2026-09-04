# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/tokenize.js
# (plus the tokenizer-relevant helpers from src/location.js and src/parseutil.js).
# Preserve the upstream licence when redistributing.
"""The tokenizer, as a mixin on the tokenizer state class.

``self.input`` is a ``domonic.javascript.String``; ``charCodeAt`` / ``.slice`` /
``.indexOf`` / ``.charAt`` / ``.substr`` / ``.length`` are all called straight
on it. As of domonic 1.6 the String models UTF-16 code units and
``charCodeAt`` past the end returns a real NaN, so no shims are needed here --
``String("").charCodeAt(n) != code`` behaves the way acorn expects.
"""

from __future__ import annotations

import math

from domonic.javascript import RegExp, String, parseFloat, parseInt

from .identifier import isIdentifierChar, isIdentifierStart
from .identifier import keywords as keyword_lists
from .locutil import Position, getLineInfo
from .tokentype import keywords as keywordTypes
from .tokentype import tt
from .whitespace import isNewLine, lineBreak, nextLineBreak, nonASCIIwhitespace, skipWhiteSpace


def _cc(s, pos):
    """``s.charCodeAt(pos)`` -- domonic 1.6 returns a numeric NaN past the end,
    which compares ``!=`` to every code and drives acorn's EOF handling."""
    return s.charCodeAt(pos)


class AcornSyntaxError(SyntaxError):
    pass


_INVALID_TEMPLATE_ESCAPE_ERROR = object()


class _InvalidTemplateEscape(Exception):
    pass


class TokenizeMixin:
    # -- error reporting (src/location.js) ---------------------------------

    def raise_(self, pos, message):
        loc = getLineInfo(self.input, pos)
        message += f" ({loc.line}:{loc.column})"
        if self.sourceFile:
            message += " in " + self.sourceFile
        err = AcornSyntaxError(message)
        err.pos = pos
        err.loc = loc
        err.raisedAt = self.pos
        raise err

    raiseRecoverable = raise_

    def unexpected(self, pos=None):
        self.raise_(pos if pos is not None else self.start, "Unexpected token")

    def curPosition(self):
        if self.options["locations"]:
            return Position(self.curLine, self.pos - self.lineStart)
        return None

    # -- strict directive (src/parseutil.js) ------------------------------

    _literal = RegExp(r"^(?:'((?:\\[^]|[^'\\])*?)'|\"((?:\\[^]|[^\"\\])*?)\")")

    def strictDirective(self, start):
        if self.options["ecmaVersion"] < 5:
            return False
        literal = self._literal
        while True:
            skipWhiteSpace.lastIndex = start
            m = skipWhiteSpace.exec(self.input)
            start += len(m[0] if m else "")
            match = literal.exec(self.input.slice(start))
            if not match:
                return False
            if (match[1] or match[2]) == "use strict":
                skipWhiteSpace.lastIndex = start + len(match[0])
                spaceAfter = skipWhiteSpace.exec(self.input)
                end = spaceAfter.index + len(spaceAfter[0])
                nxt = self.input.charAt(end)
                after = bool(lineBreak.test(spaceAfter[0])) and not (
                    bool(RegExp(r"[(`.[+\-/*%<>=,?^&]").test(nxt))
                    or (nxt == "!" and self.input.charAt(end + 1) == "=")
                    or (nxt == "i" and self._keywordOpAt(end))
                )
                return nxt == ";" or nxt == "}" or after
            start += len(match[0])
            skipWhiteSpace.lastIndex = start
            m = skipWhiteSpace.exec(self.input)
            start += len(m[0] if m else "")
            if self.input[start] == ";":
                start += 1

    def _keywordOpAt(self, pos):
        end = pos + 1
        stop = min(int(self.input.length), pos + 11)
        while end < stop:
            ch = self.fullCharCodeAt(end)
            if not isIdentifierChar(ch, True):
                break
            end += 1 if ch <= 0xFFFF else 2
        return ((end == pos + 2 and str(self.input.slice(pos, end)) == "in")
                or (end == pos + 10 and str(self.input.slice(pos, end)) == "instanceof"))

    # -- tokenizer core --------------------------------------------------

    def next(self, ignoreEscapeSequenceInKeyword=False):
        if not ignoreEscapeSequenceInKeyword and self.type.keyword and self.containsEsc:
            self.raiseRecoverable(self.start, "Escape sequence in keyword " + self.type.keyword)
        if self.options["onToken"]:
            self.options["onToken"](Token(self))
        self.lastTokEnd = self.end
        self.lastTokStart = self.start
        self.lastTokEndLoc = self.endLoc
        self.lastTokStartLoc = self.startLoc
        self.nextToken()

    def getToken(self):
        self.next()
        return Token(self)

    def __iter__(self):
        return self

    def __next__(self):
        token = self.getToken()
        if token.type is tt.eof:
            raise StopIteration
        return token

    def nextToken(self):
        curContext = self.curContext()
        if not curContext or not curContext.preserveSpace:
            self.skipSpace()
        self.start = self.pos
        if self.options["locations"]:
            self.startLoc = self.curPosition()
        if self.pos >= self.input.length:
            return self.finishToken(tt.eof)
        if curContext.override:
            return curContext.override(self)
        return self.readToken(self.fullCharCodeAtPos())

    def readToken(self, code):
        if isIdentifierStart(code, self.options["ecmaVersion"] >= 6) or code == 92:
            return self.readWord()
        return self.getTokenFromCode(code)

    def fullCharCodeAt(self, pos):
        code = _cc(self.input, pos)
        if code != code or code <= 0xD7FF or code >= 0xDC00:
            return code
        nxt = _cc(self.input, pos + 1)
        if nxt != nxt or nxt <= 0xDBFF or nxt >= 0xE000:
            return code
        return (int(code) << 10) + int(nxt) - 0x35FDC00

    def fullCharCodeAtPos(self):
        return self.fullCharCodeAt(self.pos)

    def skipBlockComment(self):
        start = self.pos
        end = self.input.indexOf("*/", self.pos + 2)
        self.pos += 2
        if end == -1:
            self.raise_(self.pos - 2, "Unterminated comment")
        self.pos = end + 2
        if self.options["locations"]:
            pos = start
            while True:
                nb = nextLineBreak(self.input, pos, self.pos)
                if nb <= -1:
                    break
                self.curLine += 1
                self.lineStart = nb
                pos = nb

    def skipLineComment(self, startSkip):
        ch = _cc(self.input, self.pos + startSkip)
        self.pos += startSkip
        while self.pos < self.input.length and not isNewLine(ch):
            self.pos += 1
            ch = _cc(self.input, self.pos)

    def skipSpace(self):
        while self.pos < self.input.length:
            ch = _cc(self.input, self.pos)
            if ch == 32 or ch == 160:
                self.pos += 1
            elif ch == 13:
                if _cc(self.input, self.pos + 1) == 10:
                    self.pos += 1
                self.pos += 1
                if self.options["locations"]:
                    self.curLine += 1
                    self.lineStart = self.pos
            elif ch == 10 or ch == 8232 or ch == 8233:
                self.pos += 1
                if self.options["locations"]:
                    self.curLine += 1
                    self.lineStart = self.pos
            elif ch == 47:
                nxt = _cc(self.input, self.pos + 1)
                if nxt == 42:
                    self.skipBlockComment()
                elif nxt == 47:
                    self.skipLineComment(2)
                else:
                    break
            else:
                if (8 < ch < 14) or (ch >= 5760 and bool(nonASCIIwhitespace.test(String.fromCharCode(ch)))):
                    self.pos += 1
                else:
                    break

    def finishToken(self, type, val=None):
        self.end = self.pos
        if self.options["locations"]:
            self.endLoc = self.curPosition()
        prevType = self.type
        self.type = type
        self.value = val
        self.updateContext(prevType)

    # -- operator sub-readers -------------------------------------------

    def readToken_dot(self):
        nxt = _cc(self.input, self.pos + 1)
        if 48 <= nxt <= 57:
            return self.readNumber(True)
        next2 = _cc(self.input, self.pos + 2)
        if self.options["ecmaVersion"] >= 6 and nxt == 46 and next2 == 46:
            self.pos += 3
            return self.finishToken(tt.ellipsis)
        self.pos += 1
        return self.finishToken(tt.dot)

    def readToken_slash(self):
        nxt = _cc(self.input, self.pos + 1)
        if self.exprAllowed:
            self.pos += 1
            return self.readRegexp()
        if nxt == 61:
            return self.finishOp(tt.assign, 2)
        return self.finishOp(tt.slash, 1)

    def readToken_mult_modulo_exp(self, code):
        nxt = _cc(self.input, self.pos + 1)
        size = 1
        tokentype = tt.star if code == 42 else tt.modulo
        if self.options["ecmaVersion"] >= 7 and code == 42 and nxt == 42:
            size += 1
            tokentype = tt.starstar
            nxt = _cc(self.input, self.pos + 2)
        if nxt == 61:
            return self.finishOp(tt.assign, size + 1)
        return self.finishOp(tokentype, size)

    def readToken_pipe_amp(self, code):
        nxt = _cc(self.input, self.pos + 1)
        if nxt == code:
            if self.options["ecmaVersion"] >= 12:
                if _cc(self.input, self.pos + 2) == 61:
                    return self.finishOp(tt.assign, 3)
            return self.finishOp(tt.logicalOR if code == 124 else tt.logicalAND, 2)
        if nxt == 61:
            return self.finishOp(tt.assign, 2)
        return self.finishOp(tt.bitwiseOR if code == 124 else tt.bitwiseAND, 1)

    def readToken_caret(self):
        nxt = _cc(self.input, self.pos + 1)
        if nxt == 61:
            return self.finishOp(tt.assign, 2)
        return self.finishOp(tt.bitwiseXOR, 1)

    def readToken_plus_min(self, code):
        nxt = _cc(self.input, self.pos + 1)
        if nxt == code:
            if (nxt == 45 and not self.inModule and _cc(self.input, self.pos + 2) == 62
                    and (self.lastTokEnd == 0 or bool(lineBreak.test(self.input.slice(self.lastTokEnd, self.pos))))):
                self.skipLineComment(3)
                self.skipSpace()
                return self.nextToken()
            return self.finishOp(tt.incDec, 2)
        if nxt == 61:
            return self.finishOp(tt.assign, 2)
        return self.finishOp(tt.plusMin, 1)

    def readToken_lt_gt(self, code):
        nxt = _cc(self.input, self.pos + 1)
        size = 1
        if nxt == code:
            size = 3 if (code == 62 and _cc(self.input, self.pos + 2) == 62) else 2
            if _cc(self.input, self.pos + size) == 61:
                return self.finishOp(tt.assign, size + 1)
            return self.finishOp(tt.bitShift, size)
        if (nxt == 33 and code == 60 and not self.inModule and _cc(self.input, self.pos + 2) == 45
                and _cc(self.input, self.pos + 3) == 45):
            self.skipLineComment(4)
            self.skipSpace()
            return self.nextToken()
        if nxt == 61:
            size = 2
        return self.finishOp(tt.relational, size)

    def readToken_eq_excl(self, code):
        nxt = _cc(self.input, self.pos + 1)
        if nxt == 61:
            return self.finishOp(tt.equality, 3 if _cc(self.input, self.pos + 2) == 61 else 2)
        if code == 61 and nxt == 62 and self.options["ecmaVersion"] >= 6:
            self.pos += 2
            return self.finishToken(tt.arrow)
        return self.finishOp(tt.eq if code == 61 else tt.prefix, 1)

    def readToken_question(self):
        ecmaVersion = self.options["ecmaVersion"]
        if ecmaVersion >= 11:
            nxt = _cc(self.input, self.pos + 1)
            if nxt == 46:
                next2 = _cc(self.input, self.pos + 2)
                if next2 != next2 or next2 < 48 or next2 > 57:
                    return self.finishOp(tt.questionDot, 2)
            if nxt == 63:
                if ecmaVersion >= 12 and _cc(self.input, self.pos + 2) == 61:
                    return self.finishOp(tt.assign, 3)
                return self.finishOp(tt.coalesce, 2)
        return self.finishOp(tt.question, 1)

    def readToken_numberSign(self):
        ecmaVersion = self.options["ecmaVersion"]
        code = 35
        if ecmaVersion >= 13:
            self.pos += 1
            code = self.fullCharCodeAtPos()
            if isIdentifierStart(code, True) or code == 92:
                return self.finishToken(tt.privateId, self.readWord1())
        from .util import codePointToString
        self.raise_(self.pos, "Unexpected character '" + codePointToString(code) + "'")

    def getTokenFromCode(self, code):
        if code == 46:
            return self.readToken_dot()
        if code == 40:
            self.pos += 1
            return self.finishToken(tt.parenL)
        if code == 41:
            self.pos += 1
            return self.finishToken(tt.parenR)
        if code == 59:
            self.pos += 1
            return self.finishToken(tt.semi)
        if code == 44:
            self.pos += 1
            return self.finishToken(tt.comma)
        if code == 91:
            self.pos += 1
            return self.finishToken(tt.bracketL)
        if code == 93:
            self.pos += 1
            return self.finishToken(tt.bracketR)
        if code == 123:
            self.pos += 1
            return self.finishToken(tt.braceL)
        if code == 125:
            self.pos += 1
            return self.finishToken(tt.braceR)
        if code == 58:
            self.pos += 1
            return self.finishToken(tt.colon)
        if code == 96:
            if self.options["ecmaVersion"] < 6:
                pass
            else:
                self.pos += 1
                return self.finishToken(tt.backQuote)
        if code == 48:
            nxt = _cc(self.input, self.pos + 1)
            if nxt == 120 or nxt == 88:
                return self.readRadixNumber(16)
            if self.options["ecmaVersion"] >= 6:
                if nxt == 111 or nxt == 79:
                    return self.readRadixNumber(8)
                if nxt == 98 or nxt == 66:
                    return self.readRadixNumber(2)
            return self.readNumber(False)
        if 49 <= code <= 57:
            return self.readNumber(False)
        if code == 34 or code == 39:
            return self.readString(code)
        if code == 47:
            return self.readToken_slash()
        if code == 37 or code == 42:
            return self.readToken_mult_modulo_exp(code)
        if code == 124 or code == 38:
            return self.readToken_pipe_amp(code)
        if code == 94:
            return self.readToken_caret()
        if code == 43 or code == 45:
            return self.readToken_plus_min(code)
        if code == 60 or code == 62:
            return self.readToken_lt_gt(code)
        if code == 61 or code == 33:
            return self.readToken_eq_excl(code)
        if code == 63:
            return self.readToken_question()
        if code == 126:
            return self.finishOp(tt.prefix, 1)
        if code == 35:
            return self.readToken_numberSign()
        from .util import codePointToString
        self.raise_(self.pos, "Unexpected character '" + codePointToString(int(code) if code == code else 0) + "'")

    def finishOp(self, type, size):
        s = self.input.slice(self.pos, self.pos + size)
        self.pos += size
        return self.finishToken(type, str(s))

    # -- regexp literal -------------------------------------------------

    def readRegexp(self):
        escaped = False
        inClass = False
        start = self.pos
        while True:
            if self.pos >= self.input.length:
                self.raise_(start, "Unterminated regular expression")
            ch = self.input.charAt(self.pos)
            if bool(lineBreak.test(ch)):
                self.raise_(start, "Unterminated regular expression")
            if not escaped:
                if ch == "[":
                    inClass = True
                elif ch == "]" and inClass:
                    inClass = False
                elif ch == "/" and not inClass:
                    break
                escaped = ch == "\\"
            else:
                escaped = False
            self.pos += 1
        pattern = str(self.input.slice(start, self.pos))
        self.pos += 1
        flagsStart = self.pos
        flags = self.readWord1()
        if self.containsEsc:
            self.unexpected(flagsStart)

        # Validate pattern (src/regexp.js).
        from .regexp import RegExpValidationState
        state = self.regexpState
        if state is None:
            state = self.regexpState = RegExpValidationState(self)
        state.reset(start, pattern, flags)
        self.validateRegExpFlags(state)
        self.validateRegExpPattern(state)

        # ESTree wants null if RegExp() can't be instantiated.
        value = None
        try:
            value = RegExp(pattern, flags)
        except Exception:
            value = None
        return self.finishToken(tt.regexp, {"pattern": pattern, "flags": flags, "value": value})

    # -- numbers ------------------------------------------------------

    def readInt(self, radix, length=None, maybeLegacyOctalNumericLiteral=False):
        allowSeparators = self.options["ecmaVersion"] >= 12 and length is None
        isLegacyOctalNumericLiteral = maybeLegacyOctalNumericLiteral and _cc(self.input, self.pos) == 48
        start = self.pos
        total = 0
        lastCode = 0
        e = math.inf if length is None else length
        i = 0
        while i < e:
            code = _cc(self.input, self.pos)
            if allowSeparators and code == 95:
                if isLegacyOctalNumericLiteral:
                    self.raiseRecoverable(self.pos, "Numeric separator is not allowed in legacy octal numeric literals")
                if lastCode == 95:
                    self.raiseRecoverable(self.pos, "Numeric separator must be exactly one underscore")
                if i == 0:
                    self.raiseRecoverable(self.pos, "Numeric separator is not allowed at the first of digits")
                lastCode = code
                i += 1
                self.pos += 1
                continue
            if code != code:
                val = math.inf
            elif code >= 97:
                val = code - 97 + 10
            elif code >= 65:
                val = code - 65 + 10
            elif 48 <= code <= 57:
                val = code - 48
            else:
                val = math.inf
            if val >= radix:
                break
            lastCode = code
            total = total * radix + val
            i += 1
            self.pos += 1
        if allowSeparators and lastCode == 95:
            self.raiseRecoverable(self.pos - 1, "Numeric separator is not allowed at the last of digits")
        if self.pos == start or (length is not None and self.pos - start != length):
            return None
        return total

    def readRadixNumber(self, radix):
        start = self.pos
        self.pos += 2
        val = self.readInt(radix)
        if val is None:
            self.raise_(self.start + 2, "Expected number in radix " + str(radix))
        if self.options["ecmaVersion"] >= 11 and _cc(self.input, self.pos) == 110:
            val = _string_to_bigint(str(self.input.slice(start, self.pos)))
            self.pos += 1
        elif isIdentifierStart(self.fullCharCodeAtPos()):
            self.raise_(self.pos, "Identifier directly after number")
        return self.finishToken(tt.num, val)

    def readNumber(self, startsWithDot):
        start = self.pos
        if not startsWithDot and self.readInt(10, None, True) is None:
            self.raise_(start, "Invalid number")
        octal = self.pos - start >= 2 and _cc(self.input, start) == 48
        if octal and self.strict:
            self.raise_(start, "Invalid number")
        nxt = _cc(self.input, self.pos)
        if not octal and not startsWithDot and self.options["ecmaVersion"] >= 11 and nxt == 110:
            val = _string_to_bigint(str(self.input.slice(start, self.pos)))
            self.pos += 1
            if isIdentifierStart(self.fullCharCodeAtPos()):
                self.raise_(self.pos, "Identifier directly after number")
            return self.finishToken(tt.num, val)
        if octal and bool(RegExp(r"[89]").test(self.input.slice(start, self.pos))):
            octal = False
        if nxt == 46 and not octal:
            self.pos += 1
            self.readInt(10)
            nxt = _cc(self.input, self.pos)
        if (nxt == 69 or nxt == 101) and not octal:
            self.pos += 1
            nxt = _cc(self.input, self.pos)
            if nxt == 43 or nxt == 45:
                self.pos += 1
            if self.readInt(10) is None:
                self.raise_(start, "Invalid number")
        if isIdentifierStart(self.fullCharCodeAtPos()):
            self.raise_(self.pos, "Identifier directly after number")
        val = _string_to_number(str(self.input.slice(start, self.pos)), octal)
        return self.finishToken(tt.num, val)

    # -- strings & escapes -------------------------------------------

    def readCodePoint(self):
        ch = _cc(self.input, self.pos)
        if ch == 123:
            if self.options["ecmaVersion"] < 6:
                self.unexpected()
            self.pos += 1
            codePos = self.pos
            code = self.readHexChar(self.input.indexOf("}", self.pos) - self.pos)
            self.pos += 1
            if code > 0x10FFFF:
                self.invalidStringToken(codePos, "Code point out of bounds")
        else:
            code = self.readHexChar(4)
        return code

    def readString(self, quote):
        out = ""
        self.pos += 1
        chunkStart = self.pos
        while True:
            if self.pos >= self.input.length:
                self.raise_(self.start, "Unterminated string constant")
            ch = _cc(self.input, self.pos)
            if ch == quote:
                break
            if ch == 92:
                out += str(self.input.slice(chunkStart, self.pos))
                out += self.readEscapedChar(False)
                chunkStart = self.pos
            elif ch == 0x2028 or ch == 0x2029:
                if self.options["ecmaVersion"] < 10:
                    self.raise_(self.start, "Unterminated string constant")
                self.pos += 1
                if self.options["locations"]:
                    self.curLine += 1
                    self.lineStart = self.pos
            else:
                if isNewLine(ch):
                    self.raise_(self.start, "Unterminated string constant")
                self.pos += 1
        out += str(self.input.slice(chunkStart, self.pos))
        self.pos += 1
        return self.finishToken(tt.string, out)

    def tryReadTemplateToken(self):
        self.inTemplateElement = True
        try:
            self.readTmplToken()
        except _InvalidTemplateEscape:
            self.readInvalidTemplateToken()
        self.inTemplateElement = False

    def invalidStringToken(self, position, message):
        if self.inTemplateElement and self.options["ecmaVersion"] >= 9:
            raise _InvalidTemplateEscape()
        self.raise_(position, message)

    def readTmplToken(self):
        out = ""
        chunkStart = self.pos
        while True:
            if self.pos >= self.input.length:
                self.raise_(self.start, "Unterminated template")
            ch = _cc(self.input, self.pos)
            if ch == 96 or (ch == 36 and _cc(self.input, self.pos + 1) == 123):
                if self.pos == self.start and (self.type is tt.template or self.type is tt.invalidTemplate):
                    if ch == 36:
                        self.pos += 2
                        return self.finishToken(tt.dollarBraceL)
                    self.pos += 1
                    return self.finishToken(tt.backQuote)
                out += str(self.input.slice(chunkStart, self.pos))
                return self.finishToken(tt.template, out)
            if ch == 92:
                out += str(self.input.slice(chunkStart, self.pos))
                out += self.readEscapedChar(True)
                chunkStart = self.pos
            elif isNewLine(ch):
                out += str(self.input.slice(chunkStart, self.pos))
                self.pos += 1
                if ch == 13:
                    if _cc(self.input, self.pos) == 10:
                        self.pos += 1
                    out += "\n"
                elif ch == 10:
                    out += "\n"
                else:
                    out += String.fromCharCode(ch)
                if self.options["locations"]:
                    self.curLine += 1
                    self.lineStart = self.pos
                chunkStart = self.pos
            else:
                self.pos += 1

    def readInvalidTemplateToken(self):
        while self.pos < self.input.length:
            c = self.input[self.pos]
            if c == "\\":
                self.pos += 1
            elif c == "$":
                if self.input[self.pos + 1:self.pos + 2] != "{":
                    pass
                else:
                    return self.finishToken(tt.invalidTemplate, str(self.input.slice(self.start, self.pos)))
            elif c == "`":
                return self.finishToken(tt.invalidTemplate, str(self.input.slice(self.start, self.pos)))
            elif c in ("\r", "\n", "\u2028", "\u2029"):
                if c == "\r" and self.input[self.pos + 1:self.pos + 2] == "\n":
                    self.pos += 1
                self.curLine += 1
                self.lineStart = self.pos + 1
            self.pos += 1
        self.raise_(self.start, "Unterminated template")

    def readEscapedChar(self, inTemplate):
        self.pos += 1
        ch = _cc(self.input, self.pos)
        self.pos += 1
        if ch == 110:
            return "\n"
        if ch == 114:
            return "\r"
        if ch == 120:
            return String.fromCharCode(self.readHexChar(2))
        if ch == 117:
            from .util import codePointToString
            return codePointToString(self.readCodePoint())
        if ch == 116:
            return "\t"
        if ch == 98:
            return "\b"
        if ch == 118:
            return "\u000b"
        if ch == 102:
            return "\f"
        if ch == 13:
            if _cc(self.input, self.pos) == 10:
                self.pos += 1
            if self.options["locations"]:
                self.lineStart = self.pos
                self.curLine += 1
            return ""
        if ch == 10:
            if self.options["locations"]:
                self.lineStart = self.pos
                self.curLine += 1
            return ""
        if ch == 56 or ch == 57:
            if self.strict:
                self.invalidStringToken(self.pos - 1, "Invalid escape sequence")
            if inTemplate:
                self.invalidStringToken(self.pos - 1, "Invalid escape sequence in template string")
        if ch == ch and 48 <= ch <= 55:
            m = RegExp(r"^[0-7]+").exec(self.input.substr(self.pos - 1, 3))
            octalStr = m[0] if m else ""
            octal = int(octalStr, 8)
            if octal > 255:
                octalStr = octalStr[:-1]
                octal = int(octalStr, 8)
            self.pos += len(octalStr) - 1
            ch = _cc(self.input, self.pos)
            if (octalStr != "0" or ch == 56 or ch == 57) and (self.strict or inTemplate):
                self.invalidStringToken(
                    self.pos - 1 - len(octalStr),
                    "Octal literal in template string" if inTemplate else "Octal literal in strict mode",
                )
            return String.fromCharCode(octal)
        if isNewLine(ch):
            if self.options["locations"]:
                self.lineStart = self.pos
                self.curLine += 1
            return ""
        return String.fromCharCode(ch)

    def readHexChar(self, length):
        codePos = self.pos
        n = self.readInt(16, length)
        if n is None:
            self.invalidStringToken(codePos, "Bad character escape sequence")
        return n

    # -- words ------------------------------------------------------

    def readWord1(self):
        self.containsEsc = False
        word = ""
        first = True
        chunkStart = self.pos
        astral = self.options["ecmaVersion"] >= 6
        while self.pos < self.input.length:
            ch = self.fullCharCodeAtPos()
            if isIdentifierChar(ch, astral):
                self.pos += 1 if ch <= 0xFFFF else 2
            elif ch == 92:
                self.containsEsc = True
                word += str(self.input.slice(chunkStart, self.pos))
                escStart = self.pos
                self.pos += 1
                if _cc(self.input, self.pos) != 117:
                    self.invalidStringToken(self.pos, "Expecting Unicode escape sequence \\uXXXX")
                self.pos += 1
                esc = self.readCodePoint()
                pred = isIdentifierStart if first else isIdentifierChar
                if not pred(esc, astral):
                    self.invalidStringToken(escStart, "Invalid Unicode escape")
                from .util import codePointToString
                word += codePointToString(esc)
                chunkStart = self.pos
            else:
                break
            first = False
        return word + str(self.input.slice(chunkStart, self.pos))

    def readWord(self):
        word = self.readWord1()
        type = tt.name
        if bool(self.keywords.test(word)):
            type = keywordTypes[word]
        return self.finishToken(type, word)


class Token:
    def __init__(self, p):
        self.type = p.type
        self.value = p.value
        self.start = p.start
        self.end = p.end

    def __repr__(self):
        return f"Token({self.type.label!r}, {self.value!r})"


def _string_to_number(s, isLegacyOctalNumericLiteral):
    if isLegacyOctalNumericLiteral:
        return parseInt(s, 8)
    clean = str(String(s).replace(RegExp("_", "g"), ""))
    # A plain integer literal stays an int (Python ints are exact Numbers and
    # print without a trailing ".0"); anything with a fraction / exponent is a
    # float, as in JS.
    if clean and all(c in "0123456789" for c in clean):
        return int(clean)
    return parseFloat(clean)


def _string_to_bigint(s):
    # domonic.javascript has no BigInt -- acorn accepts null here.
    try:
        return int(String(s).replace(RegExp("_", "g"), ""))
    except Exception:
        return None
