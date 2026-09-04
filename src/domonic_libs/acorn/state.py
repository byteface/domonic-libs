# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors the tokenizer slice
# of src/state.js's Parser constructor. Preserve the upstream licence.
"""``Tokenizer`` -- acorn's ``Parser`` cut down to just what the tokenizer needs
(no scope stack, no node factory). ``Parser.tokenizer(input, options)`` upstream
exposes exactly this surface.
"""

from __future__ import annotations

from domonic.javascript import String

from .identifier import keywords as keyword_lists
from .identifier import reservedWords
from .options import getOptions
from .regexp import RegExpValidateMixin
from .tokencontext import TokenContextMixin
from .tokenize import TokenizeMixin
from .tokentype import tt
from .util import wordsRegexp


class Tokenizer(TokenContextMixin, TokenizeMixin, RegExpValidateMixin):
    def __init__(self, options, inp, startPos=None):
        self.options = options = getOptions(options)
        self.sourceFile = options["sourceFile"]
        ev = options["ecmaVersion"]
        self.keywords = wordsRegexp(
            keyword_lists[6 if ev >= 6 else ("5module" if options["sourceType"] == "module" else 5)]
        )
        reserved = ""
        if options["allowReserved"] is not True:
            reserved = reservedWords[6 if ev >= 6 else (5 if ev == 5 else 3)]
            if options["sourceType"] == "module":
                reserved += " await"
        self.reservedWords = wordsRegexp(reserved)
        reservedStrict = (reserved + " " if reserved else "") + reservedWords["strict"]
        self.reservedWordsStrict = wordsRegexp(reservedStrict)
        self.reservedWordsStrictBind = wordsRegexp(reservedStrict + " " + reservedWords["strictBind"])

        self.input = String(inp)
        self.containsEsc = False

        self.pos = startPos or 0
        self.curLine = 1
        self.lineStart = 0
        if startPos:
            self.lineStart = self.input.lastIndexOf("\n", startPos - 1) + 1

        self.type = tt.eof
        self.value = None
        self.start = self.end = self.pos
        self.startLoc = self.endLoc = self.curPosition()

        self.lastTokEndLoc = self.lastTokStartLoc = None
        self.lastTokStart = self.lastTokEnd = self.pos

        self.context = self.initialContext()
        self.exprAllowed = True

        self.inModule = options["sourceType"] == "module"
        self.strict = self.inModule or options["strict"] is True or self.strictDirective(self.pos)

        self.potentialArrowAt = -1
        self.inTemplateElement = False
        self.regexpState = None

        if self.pos == 0 and options["allowHashBang"] and str(self.input.slice(0, 2)) == "#!":
            self.skipLineComment(2)

    # -- entry points --------------------------------------------------

    @classmethod
    def tokenizer(cls, inp, options=None):
        return cls(options, inp)

    def tokenize(self):
        """Yield every ``Token`` up to and including EOF."""
        while True:
            tok = self.getToken()
            yield tok
            if tok.type is tt.eof:
                break
