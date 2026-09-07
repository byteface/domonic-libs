# Ported from fb55/htmlparser2 (MIT). Mirrors src/Parser.ts structure.

from __future__ import annotations

from dataclasses import dataclass

from .tokenizer import QuoteType, Tokenizer


class _Undefined:
    def __repr__(self):
        return "undefined"

    __str__ = __repr__


undefined = _Undefined()


formTags = {"input", "option", "optgroup", "select", "button", "datalist", "textarea"}
pTag = {"p"}
headingTags = {"h1", "h2", "h3", "h4", "h5", "h6", "p"}
tableSectionTags = {"thead", "tbody"}
ddtTags = {"dd", "dt"}
rtpTags = {"rt", "rp"}

openImpliesClose = {
    "tr": {"tr", "th", "td"},
    "th": {"th"},
    "td": {"thead", "th", "td"},
    "body": {"head", "link", "script"},
    "a": {"a"},
    "li": {"li"},
    "p": pTag,
    "h1": headingTags,
    "h2": headingTags,
    "h3": headingTags,
    "h4": headingTags,
    "h5": headingTags,
    "h6": headingTags,
    "select": formTags,
    "input": formTags,
    "output": formTags,
    "button": formTags,
    "datalist": formTags,
    "textarea": formTags,
    "option": {"option"},
    "optgroup": {"optgroup", "option"},
    "dd": ddtTags,
    "dt": ddtTags,
    "address": pTag,
    "article": pTag,
    "aside": pTag,
    "blockquote": pTag,
    "details": pTag,
    "div": pTag,
    "dl": pTag,
    "fieldset": pTag,
    "figcaption": pTag,
    "figure": pTag,
    "footer": pTag,
    "form": pTag,
    "header": pTag,
    "hr": pTag,
    "main": pTag,
    "nav": pTag,
    "ol": pTag,
    "pre": pTag,
    "section": pTag,
    "table": pTag,
    "ul": pTag,
    "rt": rtpTags,
    "rp": rtpTags,
    "tbody": tableSectionTags,
    "tfoot": tableSectionTags,
}

DOCUMENT_TYPE = "doctype"

voidElements = {
    "area", "base", "basefont", "br", "col", "command", "embed", "frame",
    "hr", "img", "input", "isindex", "keygen", "link", "meta", "param",
    "source", "track", "wbr",
}
foreignContextElements = {"math", "svg"}
htmlIntegrationElements = {
    "mi", "mo", "mn", "ms", "mtext", "annotation-xml", "foreignObject", "desc", "title",
}
svgTagNameAdjustments = {
    "altglyph": "altGlyph", "altglyphdef": "altGlyphDef", "altglyphitem": "altGlyphItem",
    "animatecolor": "animateColor", "animatemotion": "animateMotion", "animatetransform": "animateTransform",
    "clippath": "clipPath", "feblend": "feBlend", "fecolormatrix": "feColorMatrix",
    "fecomponenttransfer": "feComponentTransfer", "fecomposite": "feComposite",
    "feconvolvematrix": "feConvolveMatrix", "fediffuselighting": "feDiffuseLighting",
    "fedisplacementmap": "feDisplacementMap", "fedistantlight": "feDistantLight",
    "fedropshadow": "feDropShadow", "feflood": "feFlood", "fefunca": "feFuncA",
    "fefuncb": "feFuncB", "fefuncg": "feFuncG", "fefuncr": "feFuncR",
    "fegaussianblur": "feGaussianBlur", "feimage": "feImage", "femerge": "feMerge",
    "femergenode": "feMergeNode", "femorphology": "feMorphology", "feoffset": "feOffset",
    "fepointlight": "fePointLight", "fespecularlighting": "feSpecularLighting",
    "fespotlight": "feSpotLight", "fetile": "feTile", "feturbulence": "feTurbulence",
    "foreignobject": "foreignObject", "glyphref": "glyphRef", "lineargradient": "linearGradient",
    "radialgradient": "radialGradient", "textpath": "textPath",
}


class ForeignContext:
    None_ = 0
    Svg = 1
    MathML = 2


@dataclass
class ParserOptions:
    xmlMode: bool = False
    decodeEntities: bool = True
    lowerCaseTags: bool | None = None
    lowerCaseAttributeNames: bool | None = None
    recognizeCDATA: bool | None = None
    recognizeSelfClosing: bool | None = None
    Tokenizer: type = Tokenizer


class Handler:
    pass


def _option_dict(options):
    if options is None:
        return {}
    if isinstance(options, ParserOptions):
        return options.__dict__.copy()
    return dict(options)


class Parser:
    _callback_names = (
        "onparserinit",
        "onreset",
        "onerror",
        "onend",
        "onopentagname",
        "onopentag",
        "onclosetag",
        "onattribute",
        "onprocessinginstruction",
        "oncomment",
        "oncommentend",
        "oncdatastart",
        "oncdataend",
        "ontext",
    )

    def __init__(self, cbs=None, options=None):
        self.options = _option_dict(options)
        self.cbs = cbs or {}
        if isinstance(self.cbs, dict):
            callbacks = {name: self.cbs.get(name) for name in self._callback_names}
        else:
            callbacks = {name: getattr(self.cbs, name, None) for name in self._callback_names}
        self._callbacks = {name: callback if callable(callback) else None for name, callback in callbacks.items()}
        self._onparserinit = self._callbacks["onparserinit"]
        self._onreset = self._callbacks["onreset"]
        self._onerror = self._callbacks["onerror"]
        self._onend = self._callbacks["onend"]
        self._onopentagname = self._callbacks["onopentagname"]
        self._onopentag = self._callbacks["onopentag"]
        self._onclosetag = self._callbacks["onclosetag"]
        self._onattribute = self._callbacks["onattribute"]
        self._onprocessinginstruction = self._callbacks["onprocessinginstruction"]
        self._oncomment = self._callbacks["oncomment"]
        self._oncommentend = self._callbacks["oncommentend"]
        self._oncdatastart = self._callbacks["oncdatastart"]
        self._oncdataend = self._callbacks["oncdataend"]
        self._ontext = self._callbacks["ontext"]
        self.startIndex = 0
        self.endIndex = 0
        self.openTagStart = 0
        self.tagname = ""
        self.attribname = ""
        self.attribvalue = ""
        self.attribs = None
        self.stack = []
        self.buffers = []
        self.bufferOffset = 0
        self.writeIndex = 0
        self.ended = False
        self.htmlMode = not bool(self.options.get("xmlMode", False))
        self.lowerCaseTagNames = self.options.get("lowerCaseTags", self.htmlMode)
        self.lowerCaseAttributeNames = self.options.get("lowerCaseAttributeNames", self.htmlMode)
        self.recognizeSelfClosing = self.options.get("recognizeSelfClosing", not self.htmlMode)
        tokenizer_cls = self.options.get("Tokenizer") or Tokenizer
        self.tokenizer = tokenizer_cls(self.options, self)
        self.foreignContext = [ForeignContext.None_]
        if self._onparserinit is not None:
            self._onparserinit(self)

    def ontext(self, start: int, endIndex: int):
        data = self.getSlice(start, endIndex)
        self.endIndex = endIndex - 1
        if self._ontext is not None:
            self._ontext(data)
        self.startIndex = endIndex

    def ontextentity(self, cp: int, endIndex: int):
        self.endIndex = endIndex - 1
        if self._ontext is not None:
            self._ontext(chr(cp))
        self.startIndex = endIndex

    def isInForeignContext(self):
        return self.foreignContext[-1] != ForeignContext.None_

    def isVoidElement(self, name: str):
        return self.htmlMode and name in voidElements

    def readTagName(self, start: int, endIndex: int):
        name = self.getSlice(start, endIndex).lower() if self.lowerCaseTagNames else self.getSlice(start, endIndex)
        if not (self.lowerCaseTagNames and self.htmlMode):
            return name
        if self.foreignContext[-1] == ForeignContext.Svg:
            return svgTagNameAdjustments.get(name) or name
        if len(self.foreignContext) > 1:
            adjusted = svgTagNameAdjustments.get(name)
            if adjusted is not None and adjusted in self.stack:
                return adjusted
        if not self.isInForeignContext():
            return "img" if name == "image" else name
        return name

    def onopentagname(self, start: int, endIndex: int):
        self.endIndex = endIndex
        self.emitOpenTag(self.readTagName(start, endIndex))

    def emitOpenTag(self, name: str):
        self.openTagStart = self.startIndex
        self.tagname = name
        if self.htmlMode and name == "form" and "form" in self.stack:
            self.tagname = ""
            return
        impliesClose = self.htmlMode and openImpliesClose.get(name)
        if impliesClose:
            while self.stack and self.stack[-1] in impliesClose:
                self.popElement(True)
        if not self.isVoidElement(name):
            self.stack.append(name)
            if self.htmlMode:
                if name == "svg":
                    self.foreignContext.append(ForeignContext.Svg)
                elif name == "math":
                    self.foreignContext.append(ForeignContext.MathML)
                elif name in htmlIntegrationElements:
                    self.foreignContext.append(ForeignContext.None_)
        if self._onopentagname is not None:
            self._onopentagname(name)
        if self._onopentag is not None:
            self.attribs = {}

    def endOpenTag(self, isImplied: bool):
        self.startIndex = self.openTagStart
        if self.attribs is not None:
            self._onopentag(self.tagname, self.attribs, isImplied)
            self.attribs = None
        if self._onclosetag is not None and self.isVoidElement(self.tagname):
            self._onclosetag(self.tagname, True)
        self.tagname = ""

    def onopentagend(self, endIndex: int):
        self.endIndex = endIndex
        self.endOpenTag(False)
        self.startIndex = endIndex + 1

    def onclosetag(self, start: int, endIndex: int):
        self.endIndex = endIndex
        name = self.readTagName(start, endIndex)
        if not self.isVoidElement(name):
            pos = -1
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index] == name:
                    pos = index
                    break
            if pos != -1:
                for _index in range(len(self.stack) - 1 - pos):
                    self.popElement(True)
                self.popElement(False)
            elif self.htmlMode and name == "p":
                self.emitOpenTag("p")
                self.closeCurrentTag(True)
        elif self.htmlMode and name == "br":
            if self._onopentagname is not None:
                self._onopentagname("br")
            if self._onopentag is not None:
                self._onopentag("br", {}, True)
            if self._onclosetag is not None:
                self._onclosetag("br", False)
        self.startIndex = endIndex + 1

    def onselfclosingtag(self, endIndex: int):
        self.endIndex = endIndex
        if self.recognizeSelfClosing or self.isInForeignContext():
            self.closeCurrentTag(False)
            self.startIndex = endIndex + 1
        else:
            self.onopentagend(endIndex)

    def popElement(self, implied: bool):
        element = self.stack.pop()
        if self.htmlMode and (element in foreignContextElements or element in htmlIntegrationElements):
            self.foreignContext.pop()
        if self._onclosetag is not None:
            self._onclosetag(element, implied)

    def closeCurrentTag(self, isOpenImplied: bool):
        name = self.tagname
        self.endOpenTag(isOpenImplied)
        if self.stack and self.stack[-1] == name:
            self.popElement(not isOpenImplied)

    def onattribname(self, start: int, endIndex: int):
        self.startIndex = start
        name = self.getSlice(start, endIndex)
        self.attribname = name.lower() if self.lowerCaseAttributeNames else name

    def onattribdata(self, start: int, endIndex: int):
        self.attribvalue += self.getSlice(start, endIndex)

    def onattribentity(self, cp: int):
        self.attribvalue += chr(cp)

    def onattribend(self, quote: QuoteType, endIndex: int):
        self.endIndex = endIndex
        value = self.attribvalue
        if self._onattribute is not None:
            quote_value = (
                '"'
                if quote == QuoteType.Double
                else "'"
                if quote == QuoteType.Single
                else undefined
                if quote == QuoteType.NoValue
                else None
            )
            self._onattribute(self.attribname, value, quote_value)
        if self.attribs is not None and self.attribname not in self.attribs:
            self.attribs[self.attribname] = value
        self.attribname = ""
        self.attribvalue = ""

    def ondeclaration(self, start: int, endIndex: int):
        value = self.getSlice(start, endIndex)
        name = value.split(None, 1)[0].lower() if value.strip() else ""
        self.endIndex = endIndex
        if name == DOCUMENT_TYPE:
            if self._onprocessinginstruction is not None:
                self._onprocessinginstruction(f"!{DOCUMENT_TYPE}", f"!{value}")
        else:
            if self._oncomment is not None:
                self._oncomment(value)
            if self._oncommentend is not None:
                self._oncommentend()
        self.startIndex = endIndex + 1

    def onprocessinginstruction(self, start: int, endIndex: int):
        value = self.getSlice(start, endIndex)
        name = value.split(None, 1)[0] if value.strip() else ""
        self.endIndex = endIndex
        if self._onprocessinginstruction is not None:
            self._onprocessinginstruction(f"?{name}", f"?{value}")
        self.startIndex = endIndex + 1

    def oncomment(self, start: int, endIndex: int, endOffset: int):
        self.endIndex = endIndex + endOffset - 1
        if self._oncomment is not None:
            self._oncomment(self.getSlice(start, endIndex))
        if self._oncommentend is not None:
            self._oncommentend()
        self.startIndex = endIndex + endOffset

    def oncdata(self, start: int, endIndex: int, endOffset: int):
        self.endIndex = endIndex + endOffset - 1
        if self.options.get("xmlMode") or self.options.get("recognizeCDATA"):
            if self._oncdatastart is not None:
                self._oncdatastart()
            if self._ontext is not None:
                self._ontext(self.getSlice(start, endIndex))
            if self._oncdataend is not None:
                self._oncdataend()
        else:
            if self._oncomment is not None:
                self._oncomment(f"[CDATA[{self.getSlice(start, endIndex)}]]")
            if self._oncommentend is not None:
                self._oncommentend()
        self.startIndex = endIndex + endOffset

    def onend(self):
        if self.attribs is not None:
            self.endOpenTag(False)
        while self.stack:
            self.popElement(True)
        if self._onend is not None:
            self._onend()

    def reset(self):
        self.startIndex = 0
        self.endIndex = 0
        self.openTagStart = 0
        self.tagname = ""
        self.attribname = ""
        self.attribvalue = ""
        self.attribs = None
        self.stack = []
        self.buffers = []
        self.bufferOffset = 0
        self.writeIndex = 0
        self.ended = False
        self.foreignContext = [ForeignContext.None_]
        self.tokenizer.reset()
        if self._onreset is not None:
            self._onreset()
        if self._onparserinit is not None:
            self._onparserinit(self)

    def parseComplete(self, data: str):
        self.reset()
        self.end(data)

    def write(self, chunk: str):
        if self.ended:
            if self._onerror is not None:
                self._onerror(ValueError(".write() after done!"))
            return
        if not isinstance(chunk, str):
            raise TypeError("Parser.write() only accepts strings")
        self.buffers.append(chunk)
        self.tokenizer.write(chunk)

    def end(self, chunk: str = ""):
        if self.ended:
            return
        if chunk:
            self.write(chunk)
        self.ended = True
        self.tokenizer.end()

    def pause(self):
        self.tokenizer.pause()

    def resume(self):
        self.tokenizer.resume()

    def done(self, chunk: str = ""):
        self.end(chunk)

    def getSlice(self, start: int, end: int):
        offset = self.tokenizer.offset
        return self.tokenizer.buffer[start - offset : end - offset]

    def _call(self, name: str, *args):
        callback = self._callbacks.get(name)
        if callback is not None:
            return callback(*args)
        return None

    def _has(self, name: str):
        return self._callbacks.get(name) is not None
