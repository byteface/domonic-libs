# Ported from cure53/DOMPurify. Preserve the upstream licence when
# redistributing. DOMPurify is (c) 2015 Mario Heiderich and released under
# Apache License 2.0 OR Mozilla Public License 2.0; see THIRD_PARTY_LICENSES.md.
# Mirrors src/purify.ts plus the src/*.ts config/regex tables.
"""Python port of DOMPurify -- an HTML/SVG/MathML sanitiser for domonic."""

from __future__ import annotations

import html
import re
from collections import defaultdict

from domonic import domonic
from domonic.dom import DocumentFragment
from domonic.javascript import RegExp, Set


NODE_TYPE = {
    "element": 1,
    "attribute": 2,
    "text": 3,
    "cdataSection": 4,
    "entityReference": 5,
    "entityNode": 6,
    "processingInstruction": 7,
    "comment": 8,
    "document": 9,
    "documentType": 10,
    "documentFragment": 11,
    "notation": 12,
}

HTML_TAGS = Set(
    [
        "a", "abbr", "acronym", "address", "area", "article", "aside", "audio",
        "b", "bdi", "bdo", "big", "blink", "blockquote", "body", "br", "button",
        "canvas", "caption", "center", "cite", "code", "col", "colgroup",
        "content", "data", "datalist", "dd", "decorator", "del", "details",
        "dfn", "dialog", "dir", "div", "dl", "dt", "element", "em",
        "fieldset", "figcaption", "figure", "font", "footer", "form", "h1",
        "h2", "h3", "h4", "h5", "h6", "head", "header", "hgroup", "hr", "html", "i", "img",
        "input", "ins", "kbd", "label", "legend", "li", "main", "map", "mark",
        "marquee", "menu", "menuitem", "meter", "nav", "nobr", "ol",
        "optgroup", "option", "output", "p", "picture", "pre", "progress", "q",
        "rp", "rt", "ruby", "s", "samp", "search", "section", "select", "selectedcontent",
        "shadow", "slot", "small", "source", "spacer", "span", "strike",
        "strong", "style", "sub", "summary", "sup", "table", "tbody", "td", "template",
        "textarea", "tfoot", "th", "thead", "time", "title", "tr", "track", "tt", "u",
        "ul", "var", "video", "wbr",
    ]
)
SVG_TAGS = Set(["svg", "a", "altglyph", "altglyphdef", "altglyphitem", "animatecolor", "animatemotion", "animatetransform", "circle", "clippath", "defs", "desc", "ellipse", "enterkeyhint", "exportparts", "filter", "font", "g", "glyph", "glyphref", "hkern", "image", "inputmode", "line", "lineargradient", "marker", "mask", "metadata", "mpath", "part", "path", "pattern", "polygon", "polyline", "radialgradient", "rect", "stop", "style", "switch", "symbol", "text", "textpath", "title", "tref", "tspan", "view", "vkern"])
SVG_FILTER_TAGS = Set(["feblend", "fecolormatrix", "fecomponenttransfer", "fecomposite", "feconvolvematrix", "fediffuselighting", "fedisplacementmap", "fedistantlight", "fedropshadow", "feflood", "fefunca", "fefuncb", "fefuncg", "fefuncr", "fegaussianblur", "feimage", "femerge", "femergenode", "femorphology", "feoffset", "fepointlight", "fespecularlighting", "fespotlight", "fetile", "feturbulence"])
SVG_DISALLOWED_TAGS = Set(["animate", "color-profile", "cursor", "discard", "font-face", "font-face-format", "font-face-name", "font-face-src", "font-face-uri", "foreignobject", "hatch", "hatchpath", "mesh", "meshgradient", "meshpatch", "meshrow", "missing-glyph", "script", "set", "solidcolor", "unknown", "use"])
MATHML_TAGS = Set(["math", "menclose", "merror", "mfenced", "mfrac", "mglyph", "mi", "mlabeledtr", "mmultiscripts", "mn", "mo", "mover", "mpadded", "mphantom", "mroot", "mrow", "ms", "mspace", "msqrt", "mstyle", "msub", "msup", "msubsup", "mtable", "mtd", "mtext", "mtr", "munder", "munderover", "mprescripts"])
MATHML_DISALLOWED_TAGS = Set(["maction", "maligngroup", "malignmark", "mlongdiv", "mscarries", "mscarry", "msgroup", "mstack", "msline", "msrow", "semantics", "annotation", "annotation-xml", "none"])
TEXT_TAGS = Set(["#text"])
ALL_SVG_TAGS = Set([*SVG_TAGS, *SVG_FILTER_TAGS, *SVG_DISALLOWED_TAGS])
ALL_MATHML_TAGS = Set([*MATHML_TAGS, *MATHML_DISALLOWED_TAGS])
HTML_ATTR = Set(
    [
        "accept", "action", "align", "alt", "autocapitalize", "autocomplete",
        "autopictureinpicture", "autoplay", "background", "bgcolor", "border",
        "capture", "cellpadding", "cellspacing", "checked", "cite", "class",
        "clear", "color", "cols", "colspan", "command", "commandfor",
        "controls", "controlslist", "coords", "crossorigin", "datetime",
        "decoding", "default", "dir", "disabled", "disablepictureinpicture",
        "disableremoteplayback", "download", "draggable", "enctype",
        "enterkeyhint", "exportparts", "face", "for", "headers", "height",
        "hidden", "high", "href", "hreflang", "id", "inert", "inputmode",
        "integrity", "ismap", "kind", "label", "lang", "list", "loading",
        "loop", "low", "max", "maxlength", "media", "method", "min",
        "minlength", "multiple", "muted", "name", "nonce", "noshade",
        "novalidate", "nowrap", "open", "optimum", "part", "pattern",
        "placeholder", "playsinline", "popover", "popovertarget",
        "popovertargetaction", "poster", "preload", "pubdate", "radiogroup",
        "readonly", "rel", "required", "rev", "reversed", "role", "rows",
        "rowspan", "scope", "selected", "shape", "size", "sizes", "slot",
        "span", "spellcheck", "srclang", "start", "src", "srcset", "step",
        "style", "summary", "tabindex", "target", "title", "translate", "type",
        "usemap", "valign", "value", "width", "wrap", "xmlns",
    ]
)
SVG_ATTR = Set(["accent-height", "accumulate", "additive", "alignment-baseline", "amplitude", "ascent", "attributename", "attributetype", "azimuth", "basefrequency", "baseline-shift", "begin", "bias", "by", "class", "clip", "clippathunits", "clip-path", "clip-rule", "color", "color-interpolation", "color-interpolation-filters", "color-profile", "color-rendering", "cx", "cy", "d", "dx", "dy", "diffuseconstant", "direction", "display", "divisor", "dominant-baseline", "dur", "edgemode", "elevation", "end", "exponent", "fill", "fill-opacity", "fill-rule", "filter", "filterunits", "flood-color", "flood-opacity", "font-family", "font-size", "font-size-adjust", "font-stretch", "font-style", "font-variant", "font-weight", "fx", "fy", "g1", "g2", "glyph-name", "glyphref", "gradientunits", "gradienttransform", "height", "href", "id", "image-rendering", "in", "in2", "intercept", "k", "k1", "k2", "k3", "k4", "kerning", "keypoints", "keysplines", "keytimes", "lang", "lengthadjust", "letter-spacing", "kernelmatrix", "kernelunitlength", "lighting-color", "local", "marker-end", "marker-mid", "marker-start", "markerheight", "markerunits", "markerwidth", "maskcontentunits", "maskunits", "max", "mask", "mask-type", "media", "method", "mode", "min", "name", "numoctaves", "offset", "operator", "opacity", "order", "orient", "orientation", "origin", "overflow", "paint-order", "path", "pathlength", "patterncontentunits", "patterntransform", "patternunits", "pointer-events", "points", "preservealpha", "preserveaspectratio", "primitiveunits", "r", "rx", "ry", "radius", "refx", "refy", "repeatcount", "repeatdur", "restart", "result", "rotate", "scale", "seed", "shape-rendering", "slope", "specularconstant", "specularexponent", "spreadmethod", "startoffset", "stddeviation", "stitchtiles", "stop-color", "stop-opacity", "stroke-dasharray", "stroke-dashoffset", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-opacity", "stroke", "stroke-width", "style", "surfacescale", "systemlanguage", "tabindex", "tablevalues", "targetx", "targety", "transform", "transform-origin", "text-anchor", "text-decoration", "text-orientation", "text-rendering", "textlength", "type", "u1", "u2", "unicode", "values", "vector-effect", "viewbox", "visibility", "version", "vert-adv-y", "vert-origin-x", "vert-origin-y", "width", "word-spacing", "wrap", "writing-mode", "xchannelselector", "ychannelselector", "x", "x1", "x2", "xmlns", "y", "y1", "y2", "z", "zoomandpan"])
MATHML_ATTR = Set(["accent", "accentunder", "align", "bevelled", "close", "columnalign", "columnlines", "columnspacing", "columnspan", "denomalign", "depth", "dir", "display", "displaystyle", "encoding", "fence", "frame", "height", "href", "id", "largeop", "length", "linethickness", "lquote", "lspace", "mathbackground", "mathcolor", "mathsize", "mathvariant", "maxsize", "minsize", "movablelimits", "notation", "numalign", "open", "rowalign", "rowlines", "rowspacing", "rowspan", "rspace", "rquote", "scriptlevel", "scriptminsize", "scriptsizemultiplier", "selection", "separator", "separators", "stretchy", "subscriptshift", "supscriptshift", "symmetric", "voffset", "width", "xmlns"])
XML_ATTR = Set(["xlink:href", "xml:id", "xlink:title", "xml:space", "xmlns:xlink"])
HTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
MATHML_NAMESPACE = "http://www.w3.org/1998/Math/MathML"
DEFAULT_ALLOWED_NAMESPACES = Set([HTML_NAMESPACE, SVG_NAMESPACE, MATHML_NAMESPACE])
DOCTYPE_RE = re.compile(r"^\s*<!doctype\s+html\s*>", re.I)
URI_ATTR = Set(["href", "src", "cite", "action", "poster", "xlink:href", "data", "formaction"])
DATA_URI_TAGS = Set(["audio", "image", "img", "source", "track", "video"])
URI_SAFE_ATTR = Set(["alt", "class", "for", "id", "label", "name", "pattern", "placeholder", "role", "style", "summary", "title", "value", "xmlns"])
FORBID_CONTENTS = Set([
    "annotation-xml", "audio", "colgroup", "desc", "foreignobject", "head",
    "iframe", "math", "mi", "mn", "mo", "ms", "mtext", "noembed",
    "noframes", "noscript", "plaintext", "script", "selectedcontent",
    "style", "svg", "template", "thead", "title", "video", "xmp",
])
LITERAL_TEXT_ELEMENTS = Set(["style", "script", "xmp", "iframe", "noembed", "noframes", "plaintext", "noscript"])
SVG_TEXT_ELEMENTS = Set(["desc", "title"])
DEFAULT_MATHML_TEXT_INTEGRATION_POINTS = Set(["mi", "mo", "mn", "ms", "mtext"])
DEFAULT_HTML_INTEGRATION_POINTS = Set(["annotation-xml"])
COMMON_SVG_AND_HTML_ELEMENTS = Set(["title", "style", "font", "a", "script"])
RESERVED_CUSTOM_ELEMENT_NAMES = Set([
    "annotation-xml",
    "color-profile",
    "font-face",
    "font-face-src",
    "font-face-uri",
    "font-face-format",
    "font-face-name",
    "missing-glyph",
])
SAFE_URI = RegExp(r"^(?:(?:(?:f|ht)tps?|mailto|tel|callto|sms|cid|xmpp|matrix):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))", "i")
DATA_URI = RegExp(
    r"^data:(?:image/(?:bmp|gif|jpeg|jpg|png|tiff|webp)|video/(?:mpeg|mp4|ogg|webm)|audio/(?:mp3|oga|ogg|opus|mpeg|wav|webm))(?:;[a-z0-9=+.\-]+)*,[a-z0-9!$&',()*+;=\-._~:/?%#\[\]@]*$",
    "i",
)
TEMPLATE_RE = re.compile(r"(\{\{[\s\S]*?\}\}|\$\{[\s\S]*?\}|<%[\s\S]*?%>)")
MUSTACHE_EXPR = re.compile(r"{{[\s\S]*|^[\s\S]*}}")
ERB_EXPR = re.compile(r"<%[\s\S]*|^[\s\S]*%>")
TMPLIT_EXPR = re.compile(r"\$\{[\s\S]*")
DATA_ATTR_RE = re.compile(r"^data-[\w.\u00b7-\uffff-]+$")
ARIA_ATTR_RE = re.compile(r"^aria-[\w-]+$")
ATTR_WHITESPACE_RE = re.compile(r"[\x00-\x20\u00a0\u1680\u180e\u2000-\u2029\u205f\u3000]+")
CSS_DANGER_RE = re.compile(r"(?:expression\s*\(|url\s*\(\s*['\"]?\s*(?:javascript|data):|-moz-binding|behavior\s*:)", re.I)
CUSTOM_ELEMENT_RE = RegExp(r"^[a-z][.\w]*(-[.\w]+)+$", "i")
LITERAL_TEXT_TAG_RE = re.compile(r"<[/!a-z]", re.I)
ATTR_MARKUP_RE = re.compile(r"((--!?|])>)|</(style|script|title|xmp|textarea|noscript|iframe|noembed|noframes)", re.I)
SCRIPT_OR_DATA_RE = RegExp(r"^(?:\w+script|data):", "i")
SELF_CLOSING_ATTR_RE = re.compile(r"/\s*>")
IS_SCRIPT_OR_DATA_RE = re.compile(r"^(?:\w+script|data):", re.I)
SANITIZE_NAMED_PROPS_PREFIX = "user-content-"
DOM_CLOBBER_NAMES = {
    "__proto__",
    "attributes",
    "children",
    "constructor",
    "contentDocument",
    "contentWindow",
    "document",
    "forms",
    "length",
    "location",
    "name",
    "nodeName",
    "parentNode",
    "prototype",
    "shadowRoot",
}

# Names DOMPurify rejects for id/name via ``value in document || value in
# formElement`` (SANITIZE_DOM). A browser resolves that against the live
# ``document`` / ``HTMLFormElement``; this is the static equivalent -- the
# properties/methods on Document, Node, Element, EventTarget and
# HTMLFormElement.
DOCUMENT_PROPERTIES = frozenset(
    """
    location documentURI URL domain referrer cookie lastModified readyState
    title dir body head images embeds plugins links forms scripts currentScript
    activeElement styleSheets pointerLockElement fullscreenElement
    pictureInPictureElement
    defaultView designMode onreadystatechange anchors applets fgColor linkColor
    vlinkColor alinkColor bgColor all scrollingElement onpointerlockchange
    onpointerlockerror hidden visibilityState wasDiscarded prerendering
    featurePolicy webkitVisibilityState webkitHidden fullscreenEnabled fullscreen
    onfullscreenchange onfullscreenerror rootElement pictureInPictureEnabled
    onbeforecopy onbeforecut onbeforepaste onfreeze onprerenderingchange
    onresume onsearch onsecuritypolicyviolation onvisibilitychange
    fonts adoptedStyleSheets fragmentDirective timeline
    implementation doctype documentElement xmlEncoding xmlVersion xmlStandalone
    inputEncoding characterSet charset compatMode contentType
    getElementsByTagName getElementsByTagNameNS getElementsByClassName
    getElementById querySelector querySelectorAll createElement createElementNS
    createDocumentFragment createTextNode createCDATASection createComment
    createProcessingInstruction createAttribute createAttributeNS createRange
    createNodeIterator createTreeWalker createEvent createExpression
    createNSResolver evaluate importNode adoptNode getElementsByName open close
    write writeln hasFocus execCommand queryCommandEnabled queryCommandIndeterm
    queryCommandState queryCommandSupported queryCommandValue clear captureEvents
    releaseEvents caretRangeFromPoint elementFromPoint elementsFromPoint
    exitFullscreen exitPointerLock getSelection webkitCancelFullScreen
    webkitExitFullscreen registerElement exitPictureInPicture getAnimations
    hasPrivateToken hasRedemptionRecord
    nodeType nodeName nodeValue textContent baseURI isConnected parentNode
    parentElement childNodes firstChild lastChild previousSibling nextSibling
    ownerDocument hasChildNodes normalize cloneNode isEqualNode isSameNode
    compareDocumentPosition contains lookupPrefix lookupNamespaceURI
    isDefaultNamespace insertBefore appendChild replaceChild removeChild
    getRootNode
    addEventListener removeEventListener dispatchEvent
    id className classList slot attributes shadowRoot part
    getAttribute getAttributeNS setAttribute setAttributeNS removeAttribute
    removeAttributeNS hasAttribute hasAttributeNS getAttributeNames
    getAttributeNode getAttributeNodeNS setAttributeNode setAttributeNodeNS
    removeAttributeNode toggleAttribute closest matches webkitMatchesSelector
    getElementsByTagName getElementsByClassName insertAdjacentElement
    insertAdjacentText insertAdjacentHTML attachShadow requestFullscreen
    requestPointerLock scrollIntoView scroll scrollTo scrollBy getBoundingClientRect
    getClientRects innerHTML outerHTML tagName prefix localName namespaceURI
    firstElementChild lastElementChild childElementCount children append prepend
    before after replaceWith replaceChildren
    action method target enctype encoding acceptCharset autocomplete name length
    elements requestSubmit reset submit checkValidity reportValidity rel relList
    noValidate
    """.split()
)
HOOK_NAMES = {
    "afterSanitizeAttributes",
    "afterSanitizeElements",
    "afterSanitizeShadowDOM",
    "beforeSanitizeAttributes",
    "beforeSanitizeElements",
    "beforeSanitizeShadowDOM",
    "uponSanitizeAttribute",
    "uponSanitizeElement",
    "uponSanitizeShadowNode",
}


import contextlib


def _node_builder_class():
    try:
        import domonic.ext.html5lib_ as _h5

        module = _h5.getDomModule(_h5.implementation)
        return next(
            v
            for v in vars(module).values()
            if isinstance(v, type) and v.__name__ == "NodeBuilder"
        )
    except Exception:  # pragma: no cover - html5lib layout changed
        return None


_NODE_BUILDER = _node_builder_class()


def _keep_whitespace_insert_text(self, data, insertBefore=None):
    if data == "":
        return
    text = self.element.ownerDocument.createTextNode(data)
    if insertBefore:
        self.element.insertBefore(text, insertBefore.element)
    else:
        self.element.appendChild(text)


@contextlib.contextmanager
def _significant_whitespace():
    """Stop domonic's html5lib tree builder discarding whitespace-only text.

    ``NodeBuilder.insertText`` returns early on ``data.isspace()``, which loses
    significant whitespace between inline / MathML / SVG children. A sanitiser
    must preserve it. Patched only for the duration of the parse. See
    ``docs/domonic-wrinkles.md``.
    """
    if _NODE_BUILDER is None:
        yield
        return
    original = _NODE_BUILDER.insertText
    _NODE_BUILDER.insertText = _keep_whitespace_insert_text
    try:
        yield
    finally:
        _NODE_BUILDER.insertText = original


def _escape_text(value):
    """HTML-escape text content the way a browser serialises ``innerHTML``."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace(" ", "&nbsp;")
    )


def _escape_attr(value):
    """HTML-escape a double-quoted attribute value (browser ``innerHTML``)."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace(" ", "&nbsp;")
    )


class _NamespaceParent:
    def __init__(self, namespace_uri, tag_name):
        self.namespaceURI = namespace_uri
        self.tagName = tag_name
        self.nodeName = tag_name


class DOMPurify:
    def __init__(self, *, is_supported=True):
        self.version = "python-port"
        self.isSupported = is_supported
        self.removed = []
        self._hooks = defaultdict(list)
        self._config = None
        self._in_trusted_types_policy = 0

    def sanitize(self, dirty, config=None):
        if not self.isSupported:
            return "" if dirty is None else str(dirty)

        cfg = dict(self._config or {})
        if config and self._config is None:
            cfg.update(config)
        self.removed = []

        prepared = self._prepare_config(cfg)
        if dirty is None:
            if prepared["return_dom"]:
                return domonic.parseString("", parser=prepared["parser"])
            return self._trusted_html("", prepared) if prepared["return_trusted_type"] else ""
        if (
            isinstance(dirty, str)
            and "<" not in dirty
            and not prepared["return_dom"]
            and not prepared["safe_for_templates"]
            and not prepared["whole_document"]
        ):
            return self._trusted_html(dirty, prepared) if prepared["return_trusted_type"] else dirty
        if cfg.get("IN_PLACE") and not isinstance(dirty, str):
            self._neutralize_patch_linkage(dirty, prepared)
            tag = self._tag(dirty)
            if tag and not self._allowed_tag(tag, prepared):
                self._neutralize_node(dirty, prepared)
                raise TypeError("root node is forbidden and cannot be sanitized in-place")
            if tag and not self._allowed_namespace(dirty, tag, prepared):
                self._neutralize_node(dirty, prepared)
                raise TypeError("root node namespace is invalid and cannot be sanitized in-place")
            if self._is_clobbered(dirty, prepared):
                self._neutralize_node(dirty, prepared)
                raise TypeError("root node is clobbered and cannot be sanitized in-place")
            clean = self._sanitize_node(dirty, prepared, dirty)
            return dirty if clean is not None else None

        source = str(dirty)
        has_safe_doctype = bool(DOCTYPE_RE.match(source))
        if prepared["safe_for_templates"]:
            source = self._strip_source_template_expressions(source)

        document = self._parse(source, prepared)
        clean = self._sanitize_node(document, prepared, document)
        if prepared["return_dom_fragment"]:
            clean = self._as_fragment(clean)
        elif prepared["return_dom"] and isinstance(clean, list):
            # body was unwrapped to a list of nodes; hand back a single node
            clean = clean[0] if len(clean) == 1 else self._as_fragment(clean)
        if prepared["return_dom"]:
            if prepared["safe_for_templates"]:
                self._scrub_template_expressions(clean)
            return clean
        html = self._serialize(clean)
        if prepared["whole_document"] and has_safe_doctype and "!doctype" in prepared["allowed_tags"]:
            html = "<!DOCTYPE html>\n" + html
        if prepared["safe_for_templates"]:
            html = self._strip_template_expressions(html, partial=False)
        if prepared["return_trusted_type"]:
            return self._trusted_html(html, prepared)
        return html

    def setConfig(self, config):
        self._config = dict(config or {})

    def clearConfig(self):
        self._config = None

    def addHook(self, name, callback):
        if name not in HOOK_NAMES or not callable(callback):
            return None
        self._hooks[name].append(callback)

    def removeHook(self, name, callback=None):
        if name not in HOOK_NAMES:
            return None
        if callback is not None:
            try:
                self._hooks[name].remove(callback)
                return callback
            except ValueError:
                return None
        if self._hooks[name]:
            return self._hooks[name].pop()
        return None

    def removeHooks(self, name):
        if name not in HOOK_NAMES:
            return None
        removed = list(self._hooks[name])
        self._hooks[name] = []
        return removed

    def removeAllHooks(self):
        self._hooks.clear()

    def isValidAttribute(self, tag, attr, value):
        cfg = self._prepare_config(self._config or {})
        return self._allowed_attr(str(attr).lower(), value, str(tag).lower(), cfg)

    def _prepare_config(self, cfg):
        cfg = self._clone_config(cfg)
        profiles = cfg.get("USE_PROFILES")
        allowed_tags = Set()
        allowed_attrs = Set()
        add_tags = cfg.get("ADD_TAGS", [])
        add_attrs = cfg.get("ADD_ATTR", [])
        add_tag_check = add_tags if callable(add_tags) else None
        add_attr_check = add_attrs if callable(add_attrs) else None
        if profiles:
            if profiles.get("html"):
                self._add_to_set(allowed_tags, HTML_TAGS)
                self._add_to_set(allowed_attrs, HTML_ATTR)
            if profiles.get("svg"):
                self._add_to_set(allowed_tags, SVG_TAGS)
                self._add_to_set(allowed_attrs, SVG_ATTR)
                self._add_to_set(allowed_attrs, XML_ATTR)
            if profiles.get("svgFilters"):
                self._add_to_set(allowed_tags, SVG_FILTER_TAGS)
                self._add_to_set(allowed_attrs, SVG_ATTR)
                self._add_to_set(allowed_attrs, XML_ATTR)
            if profiles.get("mathMl"):
                self._add_to_set(allowed_tags, MATHML_TAGS)
                self._add_to_set(allowed_attrs, MATHML_ATTR)
                self._add_to_set(allowed_attrs, XML_ATTR)
        else:
            if "ALLOWED_TAGS" in cfg:
                self._add_to_set(allowed_tags, cfg["ALLOWED_TAGS"])
            else:
                self._add_to_set(allowed_tags, HTML_TAGS)
                self._add_to_set(allowed_tags, SVG_TAGS)
                self._add_to_set(allowed_tags, SVG_FILTER_TAGS)
                self._add_to_set(allowed_tags, MATHML_TAGS)
            if "ALLOWED_ATTR" in cfg:
                self._add_to_set(allowed_attrs, cfg["ALLOWED_ATTR"])
            else:
                self._add_to_set(allowed_attrs, HTML_ATTR)
                self._add_to_set(allowed_attrs, SVG_ATTR)
                self._add_to_set(allowed_attrs, MATHML_ATTR)
                self._add_to_set(allowed_attrs, XML_ATTR)
        if not callable(add_tags):
            self._add_to_set(allowed_tags, add_tags)
        if not callable(add_attrs):
            self._add_to_set(allowed_attrs, add_attrs)
        integration_points = {name: True for name in DEFAULT_HTML_INTEGRATION_POINTS}
        integration_points.update(cfg.get("HTML_INTEGRATION_POINTS", {}) or {})
        mathml_text_points = {name: True for name in DEFAULT_MATHML_TEXT_INTEGRATION_POINTS}
        mathml_text_points.update(cfg.get("MATHML_TEXT_INTEGRATION_POINTS", {}) or {})
        namespace_tag_overrides = Set()
        for tag, enabled in integration_points.items():
            if enabled:
                tag = str(tag).lower()
                allowed_tags.add(tag)
                namespace_tag_overrides.add(tag)
        for tag, enabled in mathml_text_points.items():
            if enabled:
                tag = str(tag).lower()
                allowed_tags.add(tag)
                namespace_tag_overrides.add(tag)
        data_uri_tags = self._resolve_set_option(
            cfg,
            "ADD_DATA_URI_TAGS",
            DATA_URI_TAGS,
            transform=lambda value: str(value).lower(),
            base=DATA_URI_TAGS,
        )
        uri_safe_attrs = self._resolve_set_option(
            cfg,
            "ADD_URI_SAFE_ATTR",
            URI_SAFE_ATTR,
            transform=lambda value: str(value).lower(),
            base=URI_SAFE_ATTR,
        )
        allowed_namespaces = self._resolve_set_option(
            cfg,
            "ALLOWED_NAMESPACES",
            DEFAULT_ALLOWED_NAMESPACES,
            transform=str,
        )
        parser_media_type = self._parser_media_type(cfg)
        forbid_contents = self._resolve_set_option(
            cfg,
            "FORBID_CONTENTS",
            FORBID_CONTENTS,
            transform=lambda value: str(value).lower(),
        )
        self._add_to_set(forbid_contents, cfg.get("ADD_FORBID_CONTENTS", []))
        custom_element_handling = self._normalize_custom_element_handling(cfg)
        trusted_policy = cfg.get("TRUSTED_TYPES_POLICY")
        if trusted_policy is not None and (
            not hasattr(trusted_policy, "createHTML")
            or not callable(trusted_policy.createHTML)
            or not hasattr(trusted_policy, "createScriptURL")
            or not callable(trusted_policy.createScriptURL)
        ):
            raise TypeError('TRUSTED_TYPES_POLICY configuration option must provide "createHTML" and "createScriptURL" hooks.')
        if "table" in allowed_tags:
            allowed_tags.add("tbody")
        forbid_tags = self._resolve_set_option(
            cfg,
            "FORBID_TAGS",
            Set(),
            transform=lambda value: str(value).lower(),
        )
        if "table" in allowed_tags and "tbody" in forbid_tags:
            forbid_tags = Set(tag for tag in forbid_tags if tag != "tbody")
        forbid_attrs = self._resolve_set_option(
            cfg,
            "FORBID_ATTR",
            Set(),
            transform=lambda value: str(value).lower(),
        )
        allowed_uri_regexp = cfg.get("ALLOWED_URI_REGEXP")
        if not self._is_regex(allowed_uri_regexp):
            allowed_uri_regexp = SAFE_URI
        return_dom_fragment = cfg.get("RETURN_DOM_FRAGMENT", False)
        return_dom_import = cfg.get("RETURN_DOM_IMPORT", False)
        return {
            "allowed_tags": allowed_tags,
            "allowed_attrs": allowed_attrs,
            "forbid_tags": forbid_tags,
            "forbid_attrs": forbid_attrs,
            "allow_data_attr": self._bool_not_false(cfg, "ALLOW_DATA_ATTR") and not self._bool_option(cfg, "SAFE_FOR_TEMPLATES"),
            "allow_aria_attr": self._bool_not_false(cfg, "ALLOW_ARIA_ATTR"),
            "allow_unknown_protocols": self._bool_option(cfg, "ALLOW_UNKNOWN_PROTOCOLS"),
            "allow_self_close_in_attr": self._bool_not_false(cfg, "ALLOW_SELF_CLOSE_IN_ATTR"),
            "force_body": self._bool_option(cfg, "FORCE_BODY"),
            "keep_content": self._bool_not_false(cfg, "KEEP_CONTENT"),
            "namespace": self._namespace_option(cfg),
            "namespace_tag_overrides": namespace_tag_overrides,
            "html_integration_points": Set(integration_points.keys()),
            "mathml_text_integration_points": Set(mathml_text_points.keys()),
            "allowed_namespaces": allowed_namespaces,
            "parser_media_type": parser_media_type,
            "parser": "html.parser",
            "whole_document": self._bool_option(cfg, "WHOLE_DOCUMENT"),
            "return_dom": self._bool_option(cfg, "RETURN_DOM") or return_dom_fragment or return_dom_import,
            "return_dom_fragment": return_dom_fragment,
            "return_dom_import": return_dom_import,
            "return_trusted_type": self._bool_option(cfg, "RETURN_TRUSTED_TYPE"),
            "in_place": self._bool_option(cfg, "IN_PLACE"),
            "sanitize_dom": self._bool_not_false(cfg, "SANITIZE_DOM"),
            "sanitize_named_props": self._bool_option(cfg, "SANITIZE_NAMED_PROPS"),
            "safe_for_templates": self._bool_option(cfg, "SAFE_FOR_TEMPLATES"),
            "safe_for_xml": self._bool_not_false(cfg, "SAFE_FOR_XML"),
            "data_uri_tags": data_uri_tags,
            "uri_safe_attrs": uri_safe_attrs,
            "allowed_uri_regexp": allowed_uri_regexp,
            "add_tag_check": add_tag_check,
            "add_attr_check": add_attr_check,
            "custom_element_handling": custom_element_handling,
            "forbid_contents": forbid_contents,
            "allow_customized_builtins": custom_element_handling.get("allowCustomizedBuiltInElements", False),
            "trusted_types_policy": trusted_policy,
        }

    def _clone_config(self, cfg):
        return dict(cfg or {}) if isinstance(cfg, dict) else {}

    def _bool_option(self, cfg, key):
        return bool(cfg.get(key, False))

    def _bool_not_false(self, cfg, key):
        return cfg.get(key, True) is not False

    def _parser_media_type(self, cfg):
        value = cfg.get("PARSER_MEDIA_TYPE", "text/html")
        if value in {"text/html", "application/xhtml+xml"}:
            return value
        return "text/html"

    def _namespace_option(self, cfg):
        value = cfg.get("NAMESPACE", HTML_NAMESPACE)
        if isinstance(value, str):
            return value
        return HTML_NAMESPACE

    def _list_option_present(self, cfg, key):
        return key in cfg and isinstance(cfg[key], (list, tuple, set, Set))

    def _resolve_set_option(self, cfg, key, fallback, *, transform=str, base=None):
        if self._list_option_present(cfg, key):
            target = Set()
            if base is not None:
                self._add_values_to_set(target, base, transform)
            self._add_values_to_set(target, cfg[key], transform)
            return target
        return Set(fallback)

    def _resolve_object_option(self, cfg, key, make_fallback):
        value = cfg.get(key)
        if isinstance(value, dict):
            return dict(value)
        return make_fallback()

    def _normalize_custom_element_handling(self, cfg):
        raw = self._resolve_object_option(cfg, "CUSTOM_ELEMENT_HANDLING", dict)
        handling = {}
        tag_name_check = raw.get("tagNameCheck")
        attribute_name_check = raw.get("attributeNameCheck")
        allow_customized = raw.get("allowCustomizedBuiltInElements")
        if self._is_regex_or_function(tag_name_check):
            handling["tagNameCheck"] = tag_name_check
        if self._is_regex_or_function(attribute_name_check):
            handling["attributeNameCheck"] = attribute_name_check
        if isinstance(allow_customized, bool):
            handling["allowCustomizedBuiltInElements"] = allow_customized
        return handling

    def _sanitize_node(self, node, cfg, root=None):
        if root is None:
            root = node
        if isinstance(node, str):
            value = html.unescape(node)
            value = self._strip_template_expressions(value) if cfg["safe_for_templates"] else value
            return value  # _serialize escapes
        if self._node_type(node) == NODE_TYPE["text"]:
            value = getattr(node, "nodeValue", "") or getattr(node, "data", "") or str(node)
            value = html.unescape(str(value))
            if cfg["safe_for_templates"]:
                value = self._strip_template_expressions(value)
            # store raw; _serialize handles HTML escaping (and skips it inside
            # rawtext elements like <style>/<script>)
            node.nodeValue = value
            node.data = value
            node.args = (value,)
            return node
        if self._node_type(node) == NODE_TYPE["comment"]:
            value = getattr(node, "data", "") or str(node)
            if cfg["safe_for_xml"] and re.search(r"<[/\w!]", value):
                return self._drop_node(node, cfg, {"comment": value})
            return self._drop_node(node, cfg)
        if self._node_type(node) == NODE_TYPE["processingInstruction"]:
            value = getattr(node, "nodeValue", "") or getattr(node, "data", "") or str(node)
            if cfg["safe_for_xml"]:
                return self._drop_node(node, cfg, {"processingInstruction": value})
            return self._drop_node(node, cfg)

        tag = self._tag(node)
        is_fragment_root = not tag or tag in {"#document-fragment", "documentfragment"} or self._is_document_fragment(node)
        if not is_fragment_root and not self._allowed_namespace(node, tag, cfg):
            return self._drop_node(
                node,
                cfg,
                {"element": tag, "namespace": self._effective_namespace(node, tag, cfg)},
            )
        if tag == "head" and not cfg["whole_document"]:
            if not cfg["force_body"]:
                # DOMPurify's non-whole-document path never visits <head>
                return self._drop_node(node, cfg)
        unwrap_document_wrapper = tag in {"html", "body"} and not cfg["whole_document"]
        unwrap_forced_head = tag == "head" and cfg["force_body"] and not cfg["whole_document"]
        if self._is_unsafe_node(node, tag, cfg):
            return self._drop_node(node, cfg, {"element": tag, "unsafe": True})
        if cfg["sanitize_dom"] and self._is_clobbered(node, cfg):
            return self._drop_node(node, cfg, {"element": tag, "clobbered": True})

        parent_before_hooks = self._parent_node(node)
        self._run("beforeSanitizeElements", node, None, cfg)
        if self._handle_hook_detached_node(node, root, parent_before_hooks, cfg):
            return None
        allowed = (
            is_fragment_root
            or tag in {"html", "head", "body"} and cfg["whole_document"]
            or self._allowed_tag(tag, cfg)
        )
        cfg = self._fork_allowed_tags_for_hook(cfg)
        data = self._element_hook_event(tag, cfg)
        self._run("uponSanitizeElement", node, data, cfg)
        if self._handle_hook_detached_node(node, root, parent_before_hooks, cfg):
            return None
        if data.get("forceKeepElement"):
            allowed = True

        children = []
        for child in self._child_nodes(node):
            clean = self._sanitize_node(child, cfg, root)
            if clean is None:
                continue
            if isinstance(clean, list):
                children.extend(clean)
            else:
                children.append(clean)

        if not allowed:
            return self._sanitize_disallowed_node(node, tag, children, cfg)

        if unwrap_document_wrapper or unwrap_forced_head:
            # unwrapping the parser's html/head/body scaffold is not a removal
            return children

        self._replace_children(node, children)
        self._run("afterSanitizeElements", node, None, cfg)
        self._sanitize_attributes(node, cfg)
        self._sanitize_shadow_dom(node, cfg)
        return node

    def _allowed_tag(self, tag, cfg):
        if tag in cfg["forbid_tags"]:
            return False
        if tag in cfg["allowed_tags"]:
            return True
        if cfg["add_tag_check"] and self._call_predicate(cfg["add_tag_check"], tag):
            return True
        handling = cfg["custom_element_handling"]
        check = handling.get("tagNameCheck")
        return self._is_basic_custom_element(tag) and self._matches(check, tag)

    def _sanitize_disallowed_node(self, node, tag, children, cfg):
        if self._should_keep_disallowed_content(tag, cfg):
            self._record_removed({"element": tag})
            self._neutralize_removed_element(node, cfg, keep_children=True)
            return children
        return self._drop_node(node, cfg, {"element": tag})

    def _should_keep_disallowed_content(self, tag, cfg):
        return cfg["keep_content"] and tag not in cfg["forbid_contents"]

    def _handle_hook_detached_node(self, node, root, parent_before_hooks, cfg):
        if node is root:
            return False
        if parent_before_hooks is None:
            return False
        if self._parent_node(node) is not None:
            return False
        if cfg.get("in_place"):
            self._neutralize_removed_element(node, cfg, keep_children=False)
        return True

    def _allowed_namespace(self, node, tag, cfg):
        if not tag or tag in {"html", "head", "body"}:
            return True
        return self._check_valid_namespace(node, tag, cfg)

    def _check_svg_namespace(self, tag, parent, parent_tag, cfg):
        parent_namespace = self._effective_namespace(parent, parent_tag, cfg)
        if parent_namespace == HTML_NAMESPACE:
            return tag == "svg"
        if parent_namespace == MATHML_NAMESPACE:
            return tag == "svg" and (
                parent_tag == "annotation-xml" or parent_tag in cfg["mathml_text_integration_points"]
            )
        return tag in ALL_SVG_TAGS

    def _check_mathml_namespace(self, tag, parent, parent_tag, cfg):
        parent_namespace = self._effective_namespace(parent, parent_tag, cfg)
        if parent_namespace == HTML_NAMESPACE:
            return tag == "math"
        if parent_namespace == SVG_NAMESPACE:
            return tag == "math" and parent_tag in cfg["html_integration_points"]
        return tag in ALL_MATHML_TAGS

    def _check_html_namespace(self, tag, parent, parent_tag, cfg):
        parent_namespace = self._effective_namespace(parent, parent_tag, cfg)
        if parent_namespace == SVG_NAMESPACE and parent_tag not in cfg["html_integration_points"]:
            return False
        if parent_namespace == MATHML_NAMESPACE and parent_tag not in cfg["mathml_text_integration_points"]:
            return False
        return tag not in ALL_MATHML_TAGS and (tag in COMMON_SVG_AND_HTML_ELEMENTS or tag not in ALL_SVG_TAGS)

    def _check_valid_namespace(self, node, tag, cfg):
        parent = getattr(node, "parentNode", None)
        parent_tag = self._tag(parent)
        if not parent or parent is node or not parent_tag or parent_tag in {"#document-fragment", "documentfragment"}:
            parent = _NamespaceParent(cfg["namespace"], "template")
            parent_tag = "template"
        namespace = self._effective_namespace(node, tag, cfg)
        if namespace not in cfg["allowed_namespaces"]:
            return False
        if namespace == SVG_NAMESPACE:
            return self._check_svg_namespace(tag, parent, parent_tag, cfg)
        if namespace == MATHML_NAMESPACE:
            return self._check_mathml_namespace(tag, parent, parent_tag, cfg)
        if namespace == HTML_NAMESPACE:
            return self._check_html_namespace(tag, parent, parent_tag, cfg)
        if cfg["parser_media_type"] == "application/xhtml+xml" and namespace in cfg["allowed_namespaces"]:
            return True
        return True

    def _effective_namespace(self, node, tag, cfg):
        namespace = getattr(node, "namespaceURI", None)
        if namespace == HTML_NAMESPACE and cfg["namespace"] == SVG_NAMESPACE and (tag in SVG_TAGS or tag in SVG_FILTER_TAGS):
            return SVG_NAMESPACE
        if namespace == HTML_NAMESPACE and cfg["namespace"] == MATHML_NAMESPACE and tag in MATHML_TAGS:
            return MATHML_NAMESPACE
        if namespace:
            return namespace
        if tag in SVG_TAGS or tag in SVG_FILTER_TAGS:
            return SVG_NAMESPACE
        if tag in MATHML_TAGS:
            return MATHML_NAMESPACE
        return cfg["namespace"]

    def _sanitize_attributes(self, node, cfg):
        self._run("beforeSanitizeAttributes", node, None, cfg)
        cfg = self._fork_allowed_attrs_for_hook(cfg)
        for key, attr, value, namespace_uri in self._attribute_entries(node):
            attr_l = attr.lower()
            init_value = value
            if attr_l != "value":
                value = str(value).strip()
            data = self._attribute_hook_event(attr_l, value, cfg)
            self._run("uponSanitizeAttribute", node, data, cfg)
            new_value = data.get("attrValue", value)
            if self._should_prefix_named_prop(attr_l, new_value, cfg):
                self._remove_attribute(node, key, attr)
                new_value = SANITIZE_NAMED_PROPS_PREFIX + str(new_value)
            if self._should_drop_attr_value_for_xml(new_value, cfg):
                self._remove_sanitized_attribute(node, key, attr_l, attr)
                continue
            if attr_l == "attributename" and str(new_value).lower() == "href":
                self._remove_sanitized_attribute(node, key, attr_l, attr)
                continue
            if data.get("forceKeepAttr"):
                continue
            if not data.get("keepAttr", True):
                self._remove_sanitized_attribute(node, key, attr_l, attr)
                continue
            if not cfg["allow_self_close_in_attr"] and SELF_CLOSING_ATTR_RE.search(str(new_value)):
                self._remove_sanitized_attribute(node, key, attr_l, attr)
                continue
            allowed = self._allowed_attr(attr_l, new_value, self._tag(node), cfg)
            if not data.get("keepAttr", True) or not allowed:
                self._remove_sanitized_attribute(node, key, attr_l, attr)
            else:
                clean_value = self._clean_attr_value(attr_l, new_value, cfg)
                if attr_l in {"style", "srcset"} and not clean_value:
                    self._remove_sanitized_attribute(node, key, attr_l, attr)
                else:
                    clean_value = self._apply_trusted_types_to_attribute(
                        self._tag(node),
                        attr_l,
                        namespace_uri,
                        clean_value,
                        cfg,
                    )
                    if clean_value != init_value:
                        self._set_attribute_value(node, key, attr_l, namespace_uri, clean_value, cfg)
        self._run("afterSanitizeAttributes", node, None, cfg)

    def _attribute_entries(self, node):
        attrs = self._attributes(node)
        if attrs:
            try:
                return [
                    (
                        "_" + name,
                        name,
                        html.unescape(
                            str(node.getAttribute(name) if hasattr(node, "getAttribute") else getattr(attr, "value", ""))
                        ),
                        getattr(attr, "namespaceURI", None),
                    )
                    for name, attr in attrs
                ]
            except Exception:
                pass
        return [
            (key, key[1:] if key.startswith("_") else key, html.unescape(str(value)), None)
            for key, value in list((getattr(node, "kwargs", None) or {}).items())
        ]

    def _allowed_attr(self, attr, value, tag, cfg):
        if attr in cfg["forbid_attrs"] or attr.startswith("on"):
            return False
        if attr == "is":
            return cfg["allow_customized_builtins"] and self._matches(
                cfg["custom_element_handling"].get("tagNameCheck"), str(value)
            )
        if attr == "srcdoc":
            return False
        if self._is_patch_linkage_attribute(attr, tag, cfg):
            return False
        if (
            cfg["sanitize_dom"]
            and not cfg["sanitize_named_props"]
            and attr in {"id", "name"}
            and str(value) in DOCUMENT_PROPERTIES
        ):
            return False
        if attr.startswith("data-"):
            return cfg["allow_data_attr"] and bool(DATA_ATTR_RE.match(attr))
        if attr.startswith("aria-"):
            return cfg["allow_aria_attr"] and bool(ARIA_ATTR_RE.match(attr))
        if attr not in cfg["allowed_attrs"]:
            add_attr_allowed = cfg["add_attr_check"] and self._call_predicate(cfg["add_attr_check"], attr, tag)
            handling = cfg["custom_element_handling"]
            custom_attr_allowed = self._is_basic_custom_element(tag) and self._matches(
                handling.get("attributeNameCheck"), attr, tag
            )
            if custom_attr_allowed:
                return True
            if not add_attr_allowed:
                return False
        if not cfg["allow_self_close_in_attr"] and SELF_CLOSING_ATTR_RE.search(str(value)):
            return False
        if attr == "srcset":
            return bool(self._sanitize_srcset(str(value), cfg))

        # DOMPurify checks *every* allowed attribute's value (_isValidAttribute),
        # not just the URI-carrying ones.
        if attr in cfg["uri_safe_attrs"]:
            return True
        stripped = ATTR_WHITESPACE_RE.sub("", str(value))
        if cfg["allowed_uri_regexp"].test(stripped):
            return True
        if (
            attr in {"src", "xlink:href", "href"}
            and tag != "script"
            and str(value).startswith("data:")
            and tag in cfg["data_uri_tags"]
        ):
            return True
        if cfg["allow_unknown_protocols"] and not IS_SCRIPT_OR_DATA_RE.match(stripped):
            return True
        # only an empty (binary) value remains safe
        return not str(value)

    def _should_prefix_named_prop(self, attr, value, cfg):
        return (
            cfg["sanitize_named_props"]
            and attr in {"id", "name"}
            and not str(value).startswith(SANITIZE_NAMED_PROPS_PREFIX)
        )

    def _should_drop_attr_value_for_xml(self, value, cfg):
        return cfg["safe_for_xml"] and bool(ATTR_MARKUP_RE.search(str(value)))

    def _remove_sanitized_attribute(self, node, key, attr_l, attr_name=None):
        self._remove_attribute(node, key, attr_name or attr_l)
        self._record_removed({"attribute": attr_l, "from": self._tag(node)})

    def _apply_trusted_types_to_attribute(self, tag, attr, namespace_uri, value, cfg):
        policy = cfg["trusted_types_policy"]
        if policy is None or namespace_uri:
            return value
        get_attribute_type = getattr(policy, "getAttributeType", None)
        if not callable(get_attribute_type):
            return value
        attr_type = get_attribute_type(tag, attr)
        if attr_type == "TrustedHTML":
            return self._trusted_html(value, cfg)
        if attr_type == "TrustedScriptURL":
            return self._trusted_script_url(value, cfg)
        return value

    def _set_attribute_value(self, node, key, attr, namespace_uri, value, cfg):
        try:
            if namespace_uri and hasattr(node, "setAttributeNS"):
                node.setAttributeNS(namespace_uri, attr, value)
            else:
                self._set_attribute(node, key, attr, value)
            if cfg["sanitize_dom"] and self._is_clobbered(node, cfg):
                self._neutralize_node(node, cfg)
        except Exception:
            self._remove_sanitized_attribute(node, key, attr)

    def _is_patch_linkage_attribute(self, attr, tag, cfg):
        if not cfg["safe_for_xml"]:
            return False
        if attr == "patchsrc":
            return True
        return attr == "for" and tag not in {"label", "output"}

    def _is_basic_custom_element(self, tag):
        return tag.lower() not in RESERVED_CUSTOM_ELEMENT_NAMES and CUSTOM_ELEMENT_RE.test(tag)

    def _safe_uri(self, value, tag, cfg):
        value = ATTR_WHITESPACE_RE.sub("", value.strip())
        if value.lower().startswith("data:"):
            return tag in cfg["data_uri_tags"] and DATA_URI.test(value)
        uri_check = cfg["allowed_uri_regexp"]
        if cfg["allow_unknown_protocols"]:
            protocol = value.split(":", 1)[0].lower() if ":" in value else ""
            if protocol not in {"data", "javascript", "vbscript"}:
                return True
        return bool(uri_check.test(value))

    def _safe_srcset(self, value, tag, cfg):
        for candidate in self._split_srcset_candidates(value):
            url = candidate.strip().split()[0] if candidate.strip() else ""
            if url and not self._safe_uri(url, tag, cfg):
                return False
        return True

    def _clean_attr_value(self, attr, value, cfg):
        # Returns the raw (unescaped) value to store on the node -- DOMPurify
        # does not sanitise CSS and the browser stores DOM attribute values
        # unescaped; _serialize does the HTML escaping. Mirrors upstream, which
        # only strips whitespace inside URI-ish and srcset values.
        value = str(value)
        if cfg["safe_for_templates"]:
            value = self._strip_template_expressions(value)
        if attr in URI_ATTR:
            value = ATTR_WHITESPACE_RE.sub("", value.strip())
        if attr == "srcset":
            value = self._sanitize_srcset(value, cfg)
        return value

    def _sanitize_css(self, value):
        parts = []
        for declaration in value.split(";"):
            declaration = declaration.strip()
            if declaration and not CSS_DANGER_RE.search(declaration):
                parts.append(declaration)
        return "; ".join(parts)

    def _sanitize_srcset(self, value, cfg):
        safe = []
        for candidate in self._split_srcset_candidates(value):
            stripped = candidate.strip()
            if not stripped:
                continue
            url = stripped.split()[0]
            if self._safe_uri(url, "img", cfg):
                safe.append(stripped)
        return ", ".join(safe)

    def _split_srcset_candidates(self, value):
        candidates = []
        current = []
        for char in str(value):
            if char == ",":
                prefix = "".join(current).lstrip().lower()
                if prefix.startswith("data:") and "," not in prefix:
                    current.append(char)
                    continue
                candidates.append("".join(current))
                current = []
                continue
            current.append(char)
        candidates.append("".join(current))
        return candidates

    def _run(self, name, node, data, cfg):
        for hook in self._hooks.get(name, []):
            self._call_hook(hook, node, data, cfg)

    def _has_hooks(self, name):
        return bool(self._hooks.get(name))

    def _element_hook_event(self, tag, cfg):
        return {
            "tagName": tag,
            "allowedTags": Set(cfg["allowed_tags"]),
        }

    def _attribute_hook_event(self, attr, value, cfg):
        return {
            "attrName": attr,
            "attrValue": value,
            "keepAttr": True,
            "allowedAttributes": Set(cfg["allowed_attrs"]),
            "forceKeepAttr": None,
        }

    def _fork_allowed_tags_for_hook(self, cfg):
        if not self._has_hooks("uponSanitizeElement"):
            return cfg
        forked = dict(cfg)
        forked["allowed_tags"] = Set(cfg["allowed_tags"])
        return forked

    def _fork_allowed_attrs_for_hook(self, cfg):
        if not self._has_hooks("uponSanitizeAttribute"):
            return cfg
        forked = dict(cfg)
        forked["allowed_attrs"] = Set(cfg["allowed_attrs"])
        return forked

    def _call_hook(self, hook, node, data, cfg):
        try:
            return hook(node, data, cfg)
        except TypeError:
            try:
                return hook(node, data)
            except TypeError:
                return hook(node)

    def _sanitize_shadow_dom(self, node, cfg):
        shadow = getattr(node, "shadowRoot", None)
        if shadow is None:
            return
        self._run("beforeSanitizeShadowDOM", shadow, None, cfg)
        self._run("uponSanitizeShadowNode", shadow, {"tagName": self._tag(shadow)}, cfg)
        clean = self._sanitize_node(shadow, cfg)
        if clean is None:
            node.shadowRoot = None
        self._run("afterSanitizeShadowDOM", shadow, None, cfg)

    def _record_removed(self, record):
        if record:
            self.removed.append(record)

    def _drop_node(self, node, cfg, record=None):
        self._record_removed(record)
        if cfg.get("in_place"):
            self._neutralize_removed_element(node, cfg, keep_children=False)
        return None

    def _neutralize_removed_element(self, node, cfg, *, keep_children):
        if not self._is_node(node):
            return
        try:
            self._neutralize_subtree(node, cfg)
        except Exception:
            self._neutralize_subtree(node)
        if not keep_children:
            self._neutralize_children(node)

    def _node_type(self, node):
        try:
            return getattr(node, "nodeType", None)
        except Exception:
            return None

    def _node_name(self, node):
        try:
            return getattr(node, "tagName", None) or getattr(node, "nodeName", None) or ""
        except Exception:
            return ""

    def _is_node(self, node):
        return node is not None and (self._node_type(node) is not None or bool(self._node_name(node)))

    def _is_element(self, node):
        return self._node_type(node) == NODE_TYPE["element"] or bool(self._tag(node))

    def _is_document_fragment(self, node):
        return self._node_type(node) == NODE_TYPE["documentFragment"]

    def _is_regex(self, value):
        return value is not None and hasattr(value, "test") and callable(value.test)

    def _is_regex_or_function(self, value):
        return self._is_regex(value) or callable(value)

    def _child_nodes(self, node):
        try:
            return list(getattr(node, "childNodes", None) or getattr(node, "args", []) or [])
        except Exception:
            return []

    def _attributes(self, node):
        try:
            attrs = getattr(node, "attributes", None)
        except Exception:
            return []
        if attrs is not None and hasattr(attrs, "items"):
            try:
                return list(attrs.items())
            except Exception:
                return []
        return []

    def _strip_template_expressions(self, value, *, partial=True):
        value = str(value)
        if not partial:
            return TEMPLATE_RE.sub(" ", value)
        for expression in (MUSTACHE_EXPR, ERB_EXPR, TMPLIT_EXPR):
            value = expression.sub(" ", value)
        return value

    def _strip_source_template_expressions(self, value):
        value = self._strip_template_expressions(value, partial=False)
        value = re.sub(r"<%[^<]*", " ", value)
        value = re.sub(r"^[^<]*%>", " ", value)
        return value

    def _scrub_template_expressions(self, node):
        if node is None:
            return
        if isinstance(node, str):
            return self._strip_template_expressions(node)
        if self._node_type(node) == NODE_TYPE["text"]:
            value = getattr(node, "nodeValue", "") or getattr(node, "data", "") or str(node)
            value = self._strip_template_expressions(html.unescape(str(value)))
            node.nodeValue = value
            node.data = value
            node.args = (value,)
            return node
        for child in self._child_nodes(node):
            self._scrub_template_expressions(child)
        content = getattr(node, "content", None)
        if content is not None and content is not node:
            self._scrub_template_expressions(content)
        return node

    def _is_unsafe_node(self, node, tag, cfg):
        if not cfg["safe_for_xml"]:
            return False
        if tag in SVG_TEXT_ELEMENTS and self._effective_namespace(node, tag, cfg) == SVG_NAMESPACE:
            text = getattr(node, "textContent", "") or ""
            return bool(LITERAL_TEXT_TAG_RE.search(text))
        if tag not in LITERAL_TEXT_ELEMENTS:
            return False
        children = [child for child in self._child_nodes(node) if not isinstance(child, str)]
        if any(self._node_type(child) == NODE_TYPE["element"] for child in children):
            return True
        text = getattr(node, "textContent", "") or ""
        return bool(LITERAL_TEXT_TAG_RE.search(text))

    def _neutralize_node(self, node, cfg=None):
        self._neutralize_subtree(node, cfg)
        self._neutralize_children(node)

    def _neutralize_subtree(self, root, cfg=None):
        for node in [root, *self._element_descendants(root)]:
            if not self._is_element(node):
                continue
            self._strip_disallowed_attributes(node, cfg)

    def _strip_disallowed_attributes(self, node, cfg=None):
        tag = self._tag(node)
        for key, attr, value, _namespace_uri in self._attribute_entries(node):
            attr_l = attr.lower()
            should_drop = attr_l.startswith("on")
            should_drop = should_drop or attr_l == "srcdoc"
            should_drop = should_drop or self._is_patch_linkage_attribute(
                attr_l,
                tag,
                cfg or {"safe_for_xml": True},
            )
            if cfg is not None:
                try:
                    should_drop = should_drop or not self._allowed_attr(attr_l, value, tag, cfg)
                except Exception:
                    should_drop = True
            if should_drop:
                self._remove_attribute(node, key, attr)

    def _neutralize_patch_linkage(self, root, cfg):
        if not cfg["safe_for_xml"]:
            return
        for node in [root, *self._element_descendants(root)]:
            if not self._is_element(node):
                continue
            tag = self._tag(node)
            for key, attr, _value, _namespace_uri in self._attribute_entries(node):
                attr_l = attr.lower()
                if self._is_patch_linkage_attribute(attr_l, tag, cfg):
                    self._remove_attribute(node, key, attr)

    def _neutralize_children(self, node):
        if not self._is_node(node):
            return
        try:
            self._replace_children(node, [])
        except Exception:
            try:
                node.args = tuple()
            except Exception:
                pass

    def _is_clobbered(self, node, cfg):
        # DOMPurify's _isClobbered probes a *live* DOM node whose methods /
        # nodeType read back a named child (e.g. <input name="attributes">).
        # domonic never does named-property access, so a well-formed parsed
        # node is never clobbered; the id/name attribute drop in _allowed_attr
        # (SANITIZE_DOM) is the real protection. Kept as a hook point.
        return False

    def _element_descendants(self, node):
        for child in self._child_nodes(node):
            if isinstance(child, str):
                continue
            if not self._is_node(child):
                continue
            yield child
            yield from self._element_descendants(child)

    def _parent_node(self, node):
        try:
            parent = getattr(node, "parentNode", None)
        except Exception:
            return None
        if parent is node:
            return None
        return parent

    def _force_remove(self, node):
        parent = self._parent_node(node)
        if parent is not None and hasattr(parent, "removeChild"):
            try:
                parent.removeChild(node)
                return True
            except Exception:
                pass
        if hasattr(node, "remove"):
            try:
                node.remove()
                return True
            except Exception:
                pass
        if parent is not None and hasattr(parent, "args"):
            try:
                parent.args = tuple(child for child in (parent.args or []) if child is not node)
                return True
            except Exception:
                pass
        return False

    def _replace_children(self, node, children):
        for child in list(getattr(node, "args", []) or []):
            self._force_remove(child)
        if hasattr(node, "appendChild"):
            try:
                node.args = tuple()
                for child in children:
                    node.appendChild(child)
                return
            except Exception:
                pass
        node.args = tuple(children)

    def _remove_attribute(self, node, key, attr):
        if hasattr(node, "removeAttribute"):
            try:
                node.removeAttribute(attr)
                return
            except Exception:
                pass
        if hasattr(node, "kwargs") and key in node.kwargs:
            del node.kwargs[key]

    def _set_attribute(self, node, key, attr, value):
        if hasattr(node, "setAttribute"):
            try:
                node.setAttribute(attr, value)
                return
            except Exception:
                pass
        node.kwargs[key] = value

    def _tag(self, node):
        name = self._node_name(node)
        node_type = self._node_type(node)
        if node_type in {NODE_TYPE["document"], NODE_TYPE["documentFragment"]} and str(name).lower() in {
            "#document",
            "#document-fragment",
            "documentfragment",
            "",
        }:
            return ""
        return str(name).lower()

    def _add_to_set(self, target, values):
        for value in values:
            target.add(str(value).lower())

    def _add_values_to_set(self, target, values, transform=str):
        for value in values:
            target.add(transform(value))

    def _matches(self, check, value, *args):
        if check is None:
            return False
        if callable(check):
            return self._call_predicate(check, value, *args)
        if hasattr(check, "test"):
            return bool(check.test(value))
        return bool(re.search(str(check), value))

    def _call_predicate(self, predicate, value, *args):
        try:
            return bool(predicate(value, *args))
        except TypeError:
            return bool(predicate(value))

    def _parse(self, source, cfg):
        if cfg["parser_media_type"] == "application/xhtml+xml":
            wrapped = (
                '<html xmlns="http://www.w3.org/1999/xhtml"><head></head><body>'
                + source
                + "</body></html>"
            )
            return domonic.parseString(wrapped, parser=cfg["parser"])
        # DOMPurify parses the payload as a whole document (DOMParser). The
        # bare ``<html>`` prefix forces domonic's html5lib backend into full
        # HTML5 tree construction (leading ``<style>``/``<title>`` land in
        # ``<head>``, nested ``<a>`` auto-closes) -- unless the payload already
        # opens a document.
        probe = source.lstrip().lower()
        prefix = "" if probe.startswith(("<!doctype", "<html")) else "<html>"
        with _significant_whitespace():
            return domonic.parseString(prefix + source, parser="html5lib")

    _VOID_ELEMENTS = frozenset(
        "area base br col embed hr img input link meta param source track wbr "
        "basefont bgsound frame keygen".split()
    )
    _RAWTEXT_ELEMENTS = frozenset(
        "style script xmp iframe noembed noframes plaintext noscript".split()
    )

    def _serialize(self, value):
        if value is None:
            return ""
        if isinstance(value, list):
            return "".join(self._serialize_node(item) for item in value)
        return self._serialize_node(value)

    def _serialize_node(self, node):
        if isinstance(node, str):
            return _escape_text(node)
        node_type = self._node_type(node)
        if node_type == NODE_TYPE["text"]:
            data = getattr(node, "data", None)
            if data is None:
                data = getattr(node, "nodeValue", "") or ""
            parent_tag = self._tag(getattr(node, "parentNode", None))
            return data if parent_tag in self._RAWTEXT_ELEMENTS else _escape_text(data)
        if node_type == NODE_TYPE["comment"]:
            return "<!--" + (getattr(node, "data", "") or "") + "-->"

        name = getattr(node, "tagName", None) or getattr(node, "nodeName", "") or ""
        if node_type in (NODE_TYPE["document"], NODE_TYPE["documentFragment"]) and (
            not name or name.startswith("#")
        ):
            # bare document / fragment wrapper: emit only the children
            return "".join(self._serialize_node(c) for c in self._child_nodes(node))
        if node_type != NODE_TYPE["element"] and (not name or name.startswith("#")):
            return ""
        out = ["<", name]
        for attr_name, attr_value in self._serialize_attributes(node):
            out.append(' ' + attr_name + '="' + _escape_attr(attr_value) + '"')
        out.append(">")
        if name.lower() in self._VOID_ELEMENTS:
            return "".join(out)
        for child in self._child_nodes(node):
            out.append(self._serialize_node(child))
        out.append("</" + name + ">")
        return "".join(out)

    def _serialize_attributes(self, node):
        attributes = getattr(node, "attributes", None)
        if not attributes:
            return
        try:
            items = list(attributes)
        except TypeError:
            items = []
        for attr in items:
            name = getattr(attr, "name", None)
            if name is None and isinstance(attr, (list, tuple)):
                name, value = attr
            else:
                value = getattr(attr, "value", "")
            if name:
                yield name, "" if value is None else str(value)

    def _as_fragment(self, value):
        if isinstance(value, DocumentFragment):
            return value
        fragment = DocumentFragment()
        if value is None:
            fragment.args = tuple()
        elif isinstance(value, list):
            fragment.args = tuple(value)
        else:
            fragment.args = (value,)
        return fragment

    def _trusted_html(self, value, cfg):
        policy = cfg["trusted_types_policy"]
        if policy is None:
            return value
        self._assert_not_in_trusted_types_policy()
        self._in_trusted_types_policy += 1
        try:
            return policy.createHTML(value)
        finally:
            self._in_trusted_types_policy -= 1

    def _trusted_script_url(self, value, cfg):
        policy = cfg["trusted_types_policy"]
        if policy is None:
            return value
        self._assert_not_in_trusted_types_policy()
        self._in_trusted_types_policy += 1
        try:
            return policy.createScriptURL(value)
        finally:
            self._in_trusted_types_policy -= 1

    def _assert_not_in_trusted_types_policy(self):
        if self._in_trusted_types_policy:
            raise TypeError(
                "TRUSTED_TYPES_POLICY callbacks must not call DOMPurify.sanitize recursively."
            )


def createDOMPurify(window=None):
    if window is not None:
        document = getattr(window, "document", None)
        if getattr(document, "nodeType", None) != 9 or not hasattr(window, "Element"):
            return DOMPurify(is_supported=False)
    return DOMPurify()


_default = DOMPurify()
sanitize = _default.sanitize
addHook = _default.addHook
removeHook = _default.removeHook
removeHooks = _default.removeHooks
removeAllHooks = _default.removeAllHooks
setConfig = _default.setConfig
clearConfig = _default.clearConfig
isValidAttribute = _default.isValidAttribute
version = _default.version
isSupported = _default.isSupported

__all__ = [
    "DOMPurify",
    "addHook",
    "clearConfig",
    "createDOMPurify",
    "isSupported",
    "isValidAttribute",
    "removed",
    "removeAllHooks",
    "removeHook",
    "removeHooks",
    "sanitize",
    "setConfig",
    "version",
]


def __getattr__(name):
    if name == "removed":
        return _default.removed
    raise AttributeError(name)
