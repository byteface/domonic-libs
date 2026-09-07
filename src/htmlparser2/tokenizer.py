# Ported from fb55/htmlparser2 (MIT). Mirrors src/Tokenizer.ts public shape.

from __future__ import annotations

from html.entities import html5 as html_entities


class CharCodes:
    Tab = 0x9
    NewLine = 0xA
    FormFeed = 0xC
    CarriageReturn = 0xD
    Space = 0x20
    ExclamationMark = 0x21
    Amp = 0x26
    SingleQuote = 0x27
    DoubleQuote = 0x22
    Dash = 0x2D
    Slash = 0x2F
    Gt = 0x3E
    Lt = 0x3C
    Eq = 0x3D
    Questionmark = 0x3F
    UpperA = 0x41
    LowerA = 0x61
    UpperZ = 0x5A
    LowerZ = 0x7A
    OpeningSquareBracket = 0x5B


class QuoteType:
    NoValue = 0
    Unquoted = 1
    Single = 2
    Double = 3


class State:
    Text = 1
    BeforeTagName = 2
    InTagName = 3
    InSelfClosingTag = 4
    BeforeClosingTagName = 5
    InClosingTagName = 6
    AfterClosingTagName = 7
    BeforeAttributeName = 8
    InAttributeName = 9
    AfterAttributeName = 10
    BeforeAttributeValue = 11
    InAttributeValueDq = 12
    InAttributeValueSq = 13
    InAttributeValueNq = 14
    BeforeDeclaration = 15
    InDeclaration = 16
    InProcessingInstruction = 17
    BeforeComment = 18
    CDATASequence = 19
    DeclarationSequence = 20
    InSpecialComment = 21
    InCommentLike = 22
    SpecialStartSequence = 23
    InSpecialTag = 24
    InPlainText = 25
    InEntity = 26


class Sequences:
    Empty = ()
    Cdata = tuple(b"CDATA[")
    CdataEnd = tuple(b"]]>")
    CommentEnd = tuple(b"--!>")
    Doctype = tuple(b"doctype")
    IframeEnd = tuple(b"</iframe")
    NoembedEnd = tuple(b"</noembed")
    NoframesEnd = tuple(b"</noframes")
    Plaintext = tuple(b"</plaintext")
    ScriptEnd = tuple(b"</script")
    StyleEnd = tuple(b"</style")
    TitleEnd = tuple(b"</title")
    TextareaEnd = tuple(b"</textarea")
    XmpEnd = tuple(b"</xmp")


specialStartSequences = {
    Sequences.IframeEnd[2]: Sequences.IframeEnd,
    Sequences.NoembedEnd[2]: Sequences.NoembedEnd,
    Sequences.Plaintext[2]: Sequences.Plaintext,
    Sequences.ScriptEnd[2]: Sequences.ScriptEnd,
    Sequences.TitleEnd[2]: Sequences.TitleEnd,
    Sequences.XmpEnd[2]: Sequences.XmpEnd,
}

xml_entities = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}
control_replacements = {
    0x80: 0x20AC,
    0x82: 0x201A,
    0x83: 0x0192,
    0x84: 0x201E,
    0x85: 0x2026,
    0x86: 0x2020,
    0x87: 0x2021,
    0x88: 0x02C6,
    0x89: 0x2030,
    0x8A: 0x0160,
    0x8B: 0x2039,
    0x8C: 0x0152,
    0x8E: 0x017D,
    0x91: 0x2018,
    0x92: 0x2019,
    0x93: 0x201C,
    0x94: 0x201D,
    0x95: 0x2022,
    0x96: 0x2013,
    0x97: 0x2014,
    0x98: 0x02DC,
    0x99: 0x2122,
    0x9A: 0x0161,
    0x9B: 0x203A,
    0x9C: 0x0153,
    0x9E: 0x017E,
    0x9F: 0x0178,
}


def _replace_numeric_entity(cp: int) -> int:
    if cp == 0 or cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
        return 0xFFFD
    return control_replacements.get(cp, cp)


def _consume_entity(buffer: str, start: int, xml_mode: bool, attribute: bool):
    if start + 1 >= len(buffer):
        return None
    body_start = start + 1
    if buffer[body_start] == "#":
        index = body_start + 1
        base = 10
        if index < len(buffer) and buffer[index] in "xX":
            base = 16
            index += 1
        digit_start = index
        valid = "0123456789abcdefABCDEF" if base == 16 else "0123456789"
        while index < len(buffer) and buffer[index] in valid:
            index += 1
        if index == digit_start:
            return None
        has_semi = index < len(buffer) and buffer[index] == ";"
        if xml_mode and not has_semi:
            return None
        consumed = index + 1 - start if has_semi else index - start
        cp = _replace_numeric_entity(int(buffer[digit_start:index], base))
        return chr(cp), consumed

    index = body_start
    while index < len(buffer) and buffer[index].isalnum():
        index += 1
    name = buffer[body_start:index]
    if not name:
        return None
    if xml_mode:
        if index >= len(buffer) or buffer[index] != ";":
            return None
        decoded = xml_entities.get(name)
        return (decoded, index + 1 - start) if decoded is not None else None

    for end in range(len(name), 0, -1):
        candidate = name[:end]
        key = candidate + ";"
        has_semi = body_start + end < len(buffer) and buffer[body_start + end] == ";"
        decoded = html_entities.get(key if has_semi else candidate)
        if decoded is None:
            continue
        if attribute and not has_semi and body_start + end < len(buffer):
            next_char = buffer[body_start + end]
            if next_char.isalnum() or next_char == "=":
                return None
        return decoded, end + 2 if has_semi else end + 1
    return None


WHITESPACE_CODES = {CharCodes.Space, CharCodes.NewLine, CharCodes.Tab, CharCodes.FormFeed, CharCodes.CarriageReturn}
END_TAG_SECTION_CODES = WHITESPACE_CODES | {CharCodes.Slash, CharCodes.Gt}


def isWhitespace(c: int) -> bool:
    return c in WHITESPACE_CODES


def isEndOfTagSection(c: int) -> bool:
    return c in END_TAG_SECTION_CODES


def isASCIIAlpha(c: int) -> bool:
    return (CharCodes.LowerA <= c <= CharCodes.LowerZ) or (CharCodes.UpperA <= c <= CharCodes.UpperZ)


class Tokenizer:
    def __init__(self, options=None, cbs=None):
        options = options or {}
        self.state = State.Text
        self.buffer = ""
        self.sectionStart = 0
        self.index = 0
        self.entityStart = 0
        self.baseState = State.Text
        self.isSpecial = False
        self.running = True
        self.offset = 0
        self.xmlMode = bool(options.get("xmlMode", False))
        self.decodeEntities = options.get("decodeEntities", True) is not False
        self.recognizeSelfClosing = options.get("recognizeSelfClosing", self.xmlMode)
        self.cbs = cbs
        self._onattribdata = getattr(cbs, "onattribdata", None)
        self._onattribend = getattr(cbs, "onattribend", None)
        self._onattribentity = getattr(cbs, "onattribentity", None)
        self._onattribname = getattr(cbs, "onattribname", None)
        self._oncdata = getattr(cbs, "oncdata", None)
        self._onclosetag = getattr(cbs, "onclosetag", None)
        self._ondeclaration = getattr(cbs, "ondeclaration", None)
        self._onend = getattr(cbs, "onend", None)
        self._oncomment = getattr(cbs, "oncomment", None)
        self._onopentagend = getattr(cbs, "onopentagend", None)
        self._onopentagname = getattr(cbs, "onopentagname", None)
        self._onprocessinginstruction = getattr(cbs, "onprocessinginstruction", None)
        self._onselfclosingtag = getattr(cbs, "onselfclosingtag", None)
        self._ontext = getattr(cbs, "ontext", None)
        self._ontextentity = getattr(cbs, "ontextentity", None)
        self._is_in_foreign_context = getattr(cbs, "isInForeignContext", None)
        self.currentSequence = Sequences.Empty
        self.sequenceIndex = 0
        self._state_handlers = [None] * 27
        self._state_handlers[State.Text] = self.stateText
        self._state_handlers[State.InPlainText] = self.stateInPlainText
        self._state_handlers[State.SpecialStartSequence] = self.stateSpecialStartSequence
        self._state_handlers[State.InSpecialTag] = self.stateInSpecialTag
        self._state_handlers[State.CDATASequence] = self.stateCDATASequence
        self._state_handlers[State.DeclarationSequence] = self.stateDeclarationSequence
        self._state_handlers[State.InAttributeValueDq] = self.stateInAttributeValueDoubleQuotes
        self._state_handlers[State.InAttributeName] = self.stateInAttributeName
        self._state_handlers[State.InCommentLike] = self.stateInCommentLike
        self._state_handlers[State.InSpecialComment] = self.stateInSpecialComment
        self._state_handlers[State.BeforeAttributeName] = self.stateBeforeAttributeName
        self._state_handlers[State.InTagName] = self.stateInTagName
        self._state_handlers[State.InClosingTagName] = self.stateInClosingTagName
        self._state_handlers[State.BeforeTagName] = self.stateBeforeTagName
        self._state_handlers[State.AfterAttributeName] = self.stateAfterAttributeName
        self._state_handlers[State.InAttributeValueSq] = self.stateInAttributeValueSingleQuotes
        self._state_handlers[State.BeforeAttributeValue] = self.stateBeforeAttributeValue
        self._state_handlers[State.BeforeClosingTagName] = self.stateBeforeClosingTagName
        self._state_handlers[State.AfterClosingTagName] = self.stateAfterClosingTagName
        self._state_handlers[State.InAttributeValueNq] = self.stateInAttributeValueNoQuotes
        self._state_handlers[State.InSelfClosingTag] = self.stateInSelfClosingTag
        self._state_handlers[State.InDeclaration] = self.stateInDeclaration
        self._state_handlers[State.BeforeDeclaration] = self.stateBeforeDeclaration
        self._state_handlers[State.BeforeComment] = self.stateBeforeComment
        self._state_handlers[State.InProcessingInstruction] = self.stateInProcessingInstruction

    def reset(self):
        self.state = State.Text
        self.buffer = ""
        self.sectionStart = 0
        self.index = 0
        self.entityStart = 0
        self.baseState = State.Text
        self.isSpecial = False
        self.currentSequence = Sequences.Empty
        self.sequenceIndex = 0
        self.running = True
        self.offset = 0

    def write(self, chunk: str):
        self.offset += len(self.buffer)
        self.buffer = str(chunk)
        self.parse()

    def end(self):
        if self.running:
            self.finish()

    def pause(self):
        self.running = False

    def resume(self):
        self.running = True
        if self.index < len(self.buffer) + self.offset:
            self.parse()

    def _char_code(self) -> int:
        return ord(self.buffer[self.index - self.offset])

    def _jump_to_next(self, *chars: str) -> bool:
        local = self.index - self.offset
        hits = [hit for char in chars if (hit := self.buffer.find(char, local + 1)) >= 0]
        if not hits:
            self.index = len(self.buffer) + self.offset - 1
            return False
        self.index = min(hits) + self.offset - 1
        return True

    def _jump_to_next2(self, first: str, second: str) -> bool:
        local = self.index - self.offset + 1
        first_hit = self.buffer.find(first, local)
        second_hit = self.buffer.find(second, local)
        if first_hit < 0:
            hit = second_hit
        elif second_hit < 0:
            hit = first_hit
        else:
            hit = first_hit if first_hit < second_hit else second_hit
        if hit < 0:
            self.index = len(self.buffer) + self.offset - 1
            return False
        self.index = hit + self.offset - 1
        return True

    def _jump_to_unquoted_attr_end(self):
        local = self.index - self.offset + 1
        buffer = self.buffer
        hit = len(buffer)
        for char in ("&", ">", " ", "\n", "\t", "\f", "\r"):
            found = buffer.find(char, local)
            if 0 <= found < hit:
                hit = found
        self.index = hit + self.offset - 1

    def _scan_tag_name(self):
        buffer = self.buffer
        offset = self.offset
        index = self.index
        end = len(buffer) + offset - 1
        while index < end:
            c = ord(buffer[index + 1 - offset])
            if c in END_TAG_SECTION_CODES:
                break
            index += 1
        self.index = index

    def _scan_attribute_name(self):
        buffer = self.buffer
        offset = self.offset
        index = self.index
        end = len(buffer) + offset - 1
        while index < end:
            c = ord(buffer[index + 1 - offset])
            if c == CharCodes.Eq or c in END_TAG_SECTION_CODES:
                break
            index += 1
        self.index = index

    def fastForwardTo(self, c: int) -> bool:
        hit = self.buffer.find(chr(c), self.index - self.offset + 1)
        if hit < 0:
            self.index = len(self.buffer) + self.offset - 1
            return False
        self.index = hit + self.offset
        return True

    def stateText(self, c: int):
        if c == CharCodes.Lt or (not self.decodeEntities and self.fastForwardTo(CharCodes.Lt)):
            if self.index > self.sectionStart:
                self._ontext(self.sectionStart, self.index)
            self.state = State.BeforeTagName
            self.sectionStart = self.index
        elif self.decodeEntities and c == CharCodes.Amp:
            self.startEntity()
        elif self.decodeEntities:
            self._jump_to_next2("<", "&")

    def stateInPlainText(self, c: int):
        self.index = len(self.buffer) + self.offset - 1

    def enterTagBody(self):
        if self.currentSequence == Sequences.Plaintext:
            self.currentSequence = Sequences.Empty
            self.state = State.InPlainText
        elif self.isSpecial:
            self.state = State.InSpecialTag
            self.sequenceIndex = 0
        else:
            self.state = State.Text

    def stateSpecialStartSequence(self, c: int):
        lower = c | 0x20
        if self.sequenceIndex < len(self.currentSequence):
            if lower == self.currentSequence[self.sequenceIndex]:
                self.sequenceIndex += 1
                return
            if self.sequenceIndex == 3:
                if self.currentSequence == Sequences.ScriptEnd and lower == Sequences.StyleEnd[3]:
                    self.currentSequence = Sequences.StyleEnd
                    self.sequenceIndex = 4
                    return
                if self.currentSequence == Sequences.TitleEnd and lower == Sequences.TextareaEnd[3]:
                    self.currentSequence = Sequences.TextareaEnd
                    self.sequenceIndex = 4
                    return
            elif self.sequenceIndex == 4 and self.currentSequence == Sequences.NoembedEnd and lower == Sequences.NoframesEnd[4]:
                self.currentSequence = Sequences.NoframesEnd
                self.sequenceIndex = 5
                return
        elif isEndOfTagSection(c):
            self.sequenceIndex = 0
            self.state = State.InTagName
            self.stateInTagName(c)
            return
        self.isSpecial = False
        self.currentSequence = Sequences.Empty
        self.sequenceIndex = 0
        self.state = State.InTagName
        self.stateInTagName(c)

    def stateCDATASequence(self, c: int):
        if c == Sequences.Cdata[self.sequenceIndex]:
            self.sequenceIndex += 1
            if self.sequenceIndex == len(Sequences.Cdata):
                self.state = State.InCommentLike
                self.currentSequence = Sequences.CdataEnd
                self.sequenceIndex = 0
                self.sectionStart = self.index + 1
        else:
            self.sequenceIndex = 0
            if self.xmlMode:
                self.state = State.InDeclaration
                self.stateInDeclaration(c)
            else:
                self.state = State.InSpecialComment
                self.stateInSpecialComment(c)

    def emitComment(self, offset: int):
        self._oncomment(self.sectionStart, self.index - offset, offset)
        self.sequenceIndex = 0
        self.sectionStart = self.index + 1
        self.state = State.Text

    def stateInCommentLike(self, c: int):
        if not self.xmlMode and self.currentSequence == Sequences.CommentEnd and self.sequenceIndex <= 1 and self.index == self.sectionStart + self.sequenceIndex and c == CharCodes.Gt:
            self.emitComment(self.sequenceIndex)
        elif self.currentSequence == Sequences.CommentEnd and self.sequenceIndex == 2 and c == CharCodes.Gt:
            self.emitComment(2)
        elif self.currentSequence == Sequences.CommentEnd and self.sequenceIndex == len(self.currentSequence) - 1 and c != CharCodes.Gt:
            self.sequenceIndex = int(c == CharCodes.Dash)
        elif c == self.currentSequence[self.sequenceIndex]:
            self.sequenceIndex += 1
            if self.sequenceIndex == len(self.currentSequence):
                if self.currentSequence == Sequences.CdataEnd:
                    self._oncdata(self.sectionStart, self.index - 2, 2)
                else:
                    self._oncomment(self.sectionStart, self.index - 3, 3)
                self.sequenceIndex = 0
                self.sectionStart = self.index + 1
                self.state = State.Text
        elif self.sequenceIndex == 0:
            if self.fastForwardTo(self.currentSequence[0]):
                self.sequenceIndex = 1
        elif c != self.currentSequence[self.sequenceIndex - 1]:
            self.sequenceIndex = 0

    def isTagStartChar(self, c: int):
        return not isEndOfTagSection(c) if self.xmlMode else isASCIIAlpha(c)

    def stateInSpecialTag(self, c: int):
        if self.sequenceIndex == len(self.currentSequence):
            if isEndOfTagSection(c):
                endOfText = self.index - len(self.currentSequence)
                if self.sectionStart < endOfText:
                    actualIndex = self.index
                    self.index = endOfText
                    self._ontext(self.sectionStart, endOfText)
                    self.index = actualIndex
                self.isSpecial = False
                self.sectionStart = endOfText + 2
                self.stateInClosingTagName(c)
                return
            self.sequenceIndex = 0
        if (c | 0x20) == self.currentSequence[self.sequenceIndex]:
            self.sequenceIndex += 1
        elif self.sequenceIndex == 0:
            if self.currentSequence in (Sequences.TitleEnd, Sequences.TextareaEnd):
                if self.decodeEntities and c == CharCodes.Amp:
                    self.startEntity()
            elif self.fastForwardTo(CharCodes.Lt):
                self.sequenceIndex = 1
        else:
            self.sequenceIndex = int(c == CharCodes.Lt)

    def stateBeforeTagName(self, c: int):
        if c == CharCodes.ExclamationMark:
            self.state = State.BeforeDeclaration
            self.sectionStart = self.index + 1
        elif c == CharCodes.Questionmark:
            if self.xmlMode:
                self.state = State.InProcessingInstruction
                self.sequenceIndex = 0
                self.sectionStart = self.index + 1
            else:
                self.state = State.InSpecialComment
                self.sectionStart = self.index
        elif self.isTagStartChar(c):
            self.sectionStart = self.index
            in_foreign = bool(self._is_in_foreign_context and self._is_in_foreign_context())
            special = None if self.xmlMode or in_foreign else specialStartSequences.get(c | 0x20)
            if special is None:
                self.state = State.InTagName
            else:
                self.isSpecial = True
                self.currentSequence = special
                self.sequenceIndex = 3
                self.state = State.SpecialStartSequence
        elif c == CharCodes.Slash:
            self.state = State.BeforeClosingTagName
        else:
            self.state = State.Text
            self.stateText(c)

    def stateInTagName(self, c: int):
        if isEndOfTagSection(c):
            self._onopentagname(self.sectionStart, self.index)
            self.sectionStart = -1
            self.state = State.BeforeAttributeName
            self.stateBeforeAttributeName(c)
        else:
            self._scan_tag_name()

    def stateBeforeClosingTagName(self, c: int):
        if isWhitespace(c):
            if not self.xmlMode:
                self.state = State.InSpecialComment
                self.sectionStart = self.index
        elif c == CharCodes.Gt:
            self.state = State.Text
            if not self.xmlMode:
                self.sectionStart = self.index + 1
        else:
            self.state = State.InClosingTagName if self.isTagStartChar(c) else State.InSpecialComment
            self.sectionStart = self.index

    def stateInClosingTagName(self, c: int):
        if isEndOfTagSection(c):
            self._onclosetag(self.sectionStart, self.index)
            self.sectionStart = -1
            self.state = State.AfterClosingTagName
            self.stateAfterClosingTagName(c)
        else:
            self._scan_tag_name()

    def stateAfterClosingTagName(self, c: int):
        if c == CharCodes.Gt or self.fastForwardTo(CharCodes.Gt):
            self.state = State.Text
            self.sectionStart = self.index + 1

    def stateBeforeAttributeName(self, c: int):
        if c == CharCodes.Gt:
            self._onopentagend(self.index)
            self.enterTagBody()
            self.sectionStart = self.index + 1
        elif c == CharCodes.Slash:
            self.state = State.InSelfClosingTag
        elif c not in WHITESPACE_CODES:
            self.state = State.InAttributeName
            self.sectionStart = self.index

    def stateInSelfClosingTag(self, c: int):
        if c == CharCodes.Gt:
            self._onselfclosingtag(self.index)
            self.sectionStart = self.index + 1
            if not self.recognizeSelfClosing:
                self.enterTagBody()
                return
            self.state = State.Text
            self.isSpecial = False
            self.currentSequence = Sequences.Empty
        elif not isWhitespace(c):
            self.state = State.BeforeAttributeName
            self.stateBeforeAttributeName(c)

    def stateInAttributeName(self, c: int):
        if c == CharCodes.Eq or isEndOfTagSection(c):
            self._onattribname(self.sectionStart, self.index)
            self.sectionStart = self.index
            self.state = State.AfterAttributeName
            self.stateAfterAttributeName(c)
        else:
            self._scan_attribute_name()

    def stateAfterAttributeName(self, c: int):
        if c == CharCodes.Eq:
            self.state = State.BeforeAttributeValue
        elif c == CharCodes.Slash or c == CharCodes.Gt:
            self._onattribend(QuoteType.NoValue, self.sectionStart)
            self.sectionStart = -1
            self.state = State.BeforeAttributeName
            self.stateBeforeAttributeName(c)
        elif c not in WHITESPACE_CODES:
            self._onattribend(QuoteType.NoValue, self.sectionStart)
            self.state = State.InAttributeName
            self.sectionStart = self.index

    def stateBeforeAttributeValue(self, c: int):
        if c == CharCodes.DoubleQuote:
            self.state = State.InAttributeValueDq
            self.sectionStart = self.index + 1
        elif c == CharCodes.SingleQuote:
            self.state = State.InAttributeValueSq
            self.sectionStart = self.index + 1
        elif c not in WHITESPACE_CODES:
            self.sectionStart = self.index
            self.state = State.InAttributeValueNq
            self.stateInAttributeValueNoQuotes(c)

    def handleInAttributeValue(self, c: int, quote: int):
        if c == quote or (not self.decodeEntities and self.fastForwardTo(quote)):
            self._onattribdata(self.sectionStart, self.index)
            self.sectionStart = -1
            self._onattribend(QuoteType.Double if quote == CharCodes.DoubleQuote else QuoteType.Single, self.index + 1)
            self.state = State.BeforeAttributeName
        elif self.decodeEntities and c == CharCodes.Amp:
            self.startEntity()
        elif self.decodeEntities:
            self._jump_to_next2(chr(quote), "&")

    def stateInAttributeValueDoubleQuotes(self, c: int):
        self.handleInAttributeValue(c, CharCodes.DoubleQuote)

    def stateInAttributeValueSingleQuotes(self, c: int):
        self.handleInAttributeValue(c, CharCodes.SingleQuote)

    def stateInAttributeValueNoQuotes(self, c: int):
        if isWhitespace(c) or c == CharCodes.Gt:
            self._onattribdata(self.sectionStart, self.index)
            self.sectionStart = -1
            self._onattribend(QuoteType.Unquoted, self.index)
            self.state = State.BeforeAttributeName
            self.stateBeforeAttributeName(c)
        elif self.decodeEntities and c == CharCodes.Amp:
            self.startEntity()
        elif self.decodeEntities:
            self._jump_to_unquoted_attr_end()

    def stateBeforeDeclaration(self, c: int):
        if c == CharCodes.OpeningSquareBracket:
            self.state = State.CDATASequence
            self.sequenceIndex = 0
        elif self.xmlMode:
            self.state = State.BeforeComment if c == CharCodes.Dash else State.InDeclaration
        elif (c | 0x20) == Sequences.Doctype[0]:
            self.state = State.DeclarationSequence
            self.currentSequence = Sequences.Doctype
            self.sequenceIndex = 1
        elif c == CharCodes.Gt:
            self._oncomment(self.sectionStart, self.index, 0)
            self.state = State.Text
            self.sectionStart = self.index + 1
        elif c == CharCodes.Dash:
            self.state = State.BeforeComment
        else:
            self.state = State.InSpecialComment

    def stateDeclarationSequence(self, c: int):
        if self.sequenceIndex == len(self.currentSequence):
            self.state = State.InDeclaration
            self.stateInDeclaration(c)
        elif (c | 0x20) == self.currentSequence[self.sequenceIndex]:
            self.sequenceIndex += 1
        elif c == CharCodes.Gt:
            self._oncomment(self.sectionStart, self.index, 0)
            self.state = State.Text
            self.sectionStart = self.index + 1
        else:
            self.state = State.InSpecialComment

    def stateInDeclaration(self, c: int):
        if c == CharCodes.Gt or self.fastForwardTo(CharCodes.Gt):
            self._ondeclaration(self.sectionStart, self.index)
            self.state = State.Text
            self.sectionStart = self.index + 1

    def stateInProcessingInstruction(self, c: int):
        if c == CharCodes.Questionmark:
            self.sequenceIndex = 1
        elif c == CharCodes.Gt and self.sequenceIndex == 1:
            self._onprocessinginstruction(self.sectionStart, self.index - 1)
            self.sequenceIndex = 0
            self.state = State.Text
            self.sectionStart = self.index + 1
        else:
            self.sequenceIndex = int(self.fastForwardTo(CharCodes.Questionmark))

    def stateBeforeComment(self, c: int):
        if c == CharCodes.Dash:
            self.state = State.InCommentLike
            self.currentSequence = Sequences.CommentEnd
            self.sequenceIndex = 0
            self.sectionStart = self.index + 1
        elif self.xmlMode:
            self.state = State.InDeclaration
        elif c == CharCodes.Gt:
            self._oncomment(self.sectionStart, self.index, 0)
            self.state = State.Text
            self.sectionStart = self.index + 1
        else:
            self.state = State.InSpecialComment

    def stateInSpecialComment(self, c: int):
        if c == CharCodes.Gt or self.fastForwardTo(CharCodes.Gt):
            self._oncomment(self.sectionStart, self.index, 0)
            self.state = State.Text
            self.sectionStart = self.index + 1

    def startEntity(self):
        self.baseState = self.state
        start = self.index - self.offset
        attribute = self.baseState not in (State.Text, State.InSpecialTag)
        consumed = _consume_entity(self.buffer, start, self.xmlMode, attribute)
        if consumed is None:
            return
        decoded, length = consumed
        self.entityStart = self.index
        self.emitEntity(decoded, length)

    def emitEntity(self, decoded: str, consumed: int):
        for index, char in enumerate(decoded):
            self.emitCodePoint(ord(char), consumed if index == 0 else 0)

    def emitCodePoint(self, cp: int, consumed: int):
        if self.baseState not in (State.Text, State.InSpecialTag):
            if self.sectionStart < self.entityStart:
                self._onattribdata(self.sectionStart, self.entityStart)
            self.sectionStart = self.entityStart + consumed
            self.index = self.sectionStart - 1
            self._onattribentity(cp)
        else:
            if self.sectionStart < self.entityStart:
                self._ontext(self.sectionStart, self.entityStart)
            self.sectionStart = self.entityStart + consumed
            self.index = self.sectionStart - 1
            self._ontextentity(cp, self.sectionStart)

    def cleanup(self):
        if self.running and self.sectionStart != self.index:
            if self.state in (State.Text, State.InPlainText) or (self.state == State.InSpecialTag and self.sequenceIndex == 0):
                self._ontext(self.sectionStart, self.index)
                self.sectionStart = self.index
            elif self.state in (State.InAttributeValueDq, State.InAttributeValueSq, State.InAttributeValueNq):
                self._onattribdata(self.sectionStart, self.index)
                self.sectionStart = self.index

    def shouldContinue(self):
        return self.index < len(self.buffer) + self.offset and self.running

    def parse(self):
        buffer = self.buffer
        offset = self.offset
        end = len(buffer) + offset
        handlers = self._state_handlers
        while self.index < end and self.running:
            c = ord(buffer[self.index - offset])
            handlers[self.state](c)
            self.index += 1
        self.cleanup()

    def finish(self):
        self.handleTrailingData()
        self._onend()

    def handleTrailingCommentLikeData(self, endIndex: int) -> bool:
        if self.state != State.InCommentLike:
            return False
        if self.currentSequence == Sequences.CdataEnd:
            if self.xmlMode:
                if self.sectionStart < endIndex:
                    self._oncdata(self.sectionStart, endIndex, 0)
            else:
                cdataStart = self.sectionStart - len(Sequences.Cdata) - 1
                self._oncomment(cdataStart, endIndex, 0)
        else:
            offset = 0 if self.xmlMode else min(self.sequenceIndex, len(Sequences.CommentEnd) - 1)
            self._oncomment(self.sectionStart, endIndex, offset)
        return True

    def handleTrailingMarkupDeclaration(self, endIndex: int) -> bool:
        if self.xmlMode:
            if self.state in (State.InSpecialComment, State.BeforeComment, State.CDATASequence, State.DeclarationSequence, State.InDeclaration):
                self._ontext(self.sectionStart, endIndex)
                return True
            return False
        if self.state in (State.BeforeDeclaration, State.InSpecialComment, State.BeforeComment, State.CDATASequence):
            self._oncomment(self.sectionStart, endIndex, 0)
            return True
        if self.state == State.DeclarationSequence:
            if self.sequenceIndex != len(Sequences.Doctype):
                self._oncomment(self.sectionStart, endIndex, 0)
            return True
        if self.state == State.InDeclaration:
            return True
        return False

    def handleTrailingData(self):
        endIndex = len(self.buffer) + self.offset
        if self.handleTrailingCommentLikeData(endIndex) or self.handleTrailingMarkupDeclaration(endIndex):
            return
        if self.sectionStart >= endIndex:
            return
        if self.state in (
            State.InTagName,
            State.BeforeAttributeName,
            State.BeforeAttributeValue,
            State.AfterAttributeName,
            State.InAttributeName,
            State.InAttributeValueSq,
            State.InAttributeValueDq,
            State.InAttributeValueNq,
            State.InClosingTagName,
        ):
            return
        self._ontext(self.sectionStart, endIndex)
