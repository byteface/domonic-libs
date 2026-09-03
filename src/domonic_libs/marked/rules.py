# Ported from markedjs/marked (MIT). Mirrors src/rules.ts.
"""The block and inline grammars.

marked composes its regexes from fragments with a small ``edit().replace()``
builder; that is reproduced here as :class:`_Edit`. JS ``(?<name>)`` /
``\\k<name>`` become ``(?P<name>)`` / ``(?P=name)``, ``\\p{P}`` etc. become the
character classes from :mod:`._unicode`, and the one variable-width lookbehind
(``blockSkip``) takes marked's own no-lookbehind fallback branch.
"""

from __future__ import annotations

import re

from ._unicode import P as _UP
from ._unicode import Pi as _UPI
from ._unicode import Ps as _UPS
from ._unicode import S as _US

_CARET = re.compile(r"(^|[^\[])\^")


class _NoopTest:
    def match(self, _s, _pos=0):
        return None

    def search(self, _s, _pos=0):
        return None

    def finditer(self, _s):
        return iter(())

    def sub(self, _repl, s, count=0):
        return s


noop_test = _NoopTest()


class _Edit:
    def __init__(self, regex, opt=""):
        self.source = regex if isinstance(regex, str) else regex.pattern
        self.opt = opt

    def replace(self, name, val):
        val_source = val if isinstance(val, str) else val.pattern
        val_source = _CARET.sub(lambda m: m.group(1), val_source)
        if isinstance(name, re.Pattern):
            self.source = name.sub(lambda _m: val_source, self.source)
        else:
            self.source = self.source.replace(name, val_source, 1)
        return self

    def get_regex(self):
        flags = 0
        if "i" in self.opt:
            flags |= re.I
        if "m" in self.opt:
            flags |= re.M
        if "s" in self.opt:
            flags |= re.S
        return re.compile(self.source, flags)


def _edit(regex, opt=""):
    return _Edit(regex, opt)


def _cached_indent_regex(create):
    cache = {}

    def get(indent):
        idx = max(0, min(3, indent - 1))
        if idx not in cache:
            cache[idx] = create(idx)
        return cache[idx]

    return get


# ---------------------------------------------------------------------------
# other: standalone helper regexes
# ---------------------------------------------------------------------------

other = {
    "codeRemoveIndent": re.compile(r"^(?: {1,4}| {0,3}\t)", re.M),
    "outputLinkReplace": re.compile(r"\\([\[\]])"),
    "indentCodeCompensation": re.compile(r"^(\s+)(?:```)"),
    "beginningSpace": re.compile(r"^\s+"),
    "endingHash": re.compile(r"#$"),
    "startingSpaceChar": re.compile(r"^ "),
    "endingSpaceChar": re.compile(r" $"),
    "nonSpaceChar": re.compile(r"[^ ]"),
    "newLineCharGlobal": re.compile(r"\n"),
    "tabCharGlobal": re.compile(r"\t"),
    "multipleSpaceGlobal": re.compile(r"\s+"),
    "blankLine": re.compile(r"^[ \t]*$"),
    "doubleBlankLine": re.compile(r"\n[ \t]*\n[ \t]*$"),
    "blockquoteStart": re.compile(r"^ {0,3}>"),
    "blockquoteSetextReplace": re.compile(r"\n {0,3}((?:=+|-+) *)(?=\n|$)"),
    "blockquoteSetextReplace2": re.compile(r"^ {0,3}>[ \t]?", re.M),
    "listReplaceNesting": re.compile(r"^ {1,4}(?=( {4})*[^ ])"),
    "listIsTask": re.compile(r"^\[[ xX]\] +\S"),
    "listReplaceTask": re.compile(r"^\[[ xX]\] +"),
    "listTaskCheckbox": re.compile(r"\[[ xX]\]"),
    "anyLine": re.compile(r"\n.*\n"),
    "hrefBrackets": re.compile(r"^<(.*)>$"),
    "tableDelimiter": re.compile(r"[:|]"),
    "tableAlignChars": re.compile(r"^\||\| *$"),
    "tableRowBlankLine": re.compile(r"\n[ \t]*$"),
    "tableAlignRight": re.compile(r"^ *-+: *$"),
    "tableAlignCenter": re.compile(r"^ *:-+: *$"),
    "tableAlignLeft": re.compile(r"^ *:-+ *$"),
    "startATag": re.compile(r"^<a ", re.I),
    "endATag": re.compile(r"^</a>", re.I),
    "startPreScriptTag": re.compile(r"^<(pre|code|kbd|script)(\s|>)", re.I),
    "endPreScriptTag": re.compile(r"^</(pre|code|kbd|script)(\s|>)", re.I),
    "startAngleBracket": re.compile(r"^<"),
    "endAngleBracket": re.compile(r">$"),
    "pedanticHrefTitle": re.compile(r"^([^'\"]*[^\s])\s+(['\"])(.*)\2"),
    "escapeTest": re.compile(r"[&<>\"']"),
    "escapeReplace": re.compile(r"[&<>\"']"),
    "escapeTestNoEncode": re.compile(
        r"[<>\"']|&(?!(#\d{1,7}|#[Xx][a-fA-F0-9]{1,6}|\w+);)"
    ),
    "escapeReplaceNoEncode": re.compile(
        r"[<>\"']|&(?!(#\d{1,7}|#[Xx][a-fA-F0-9]{1,6}|\w+);)"
    ),
    "caret": _CARET,
    "percentDecode": re.compile(r"%25"),
    "findPipe": re.compile(r"\|"),
    "splitPipe": re.compile(r" \|"),
    "slashPipe": re.compile(r"\\\|"),
    "carriageReturn": re.compile(r"\r\n|\r"),
    "spaceLine": re.compile(r"^ +$", re.M),
    "notSpaceStart": re.compile(r"^\S*"),
    "endingNewline": re.compile(r"\n$"),
    "unicodeAlphaNumeric": None,  # handled via _unicode.is_alpha_numeric
    "listItemRegex": lambda bull: re.compile(
        r"^( {0,3}" + bull + r")((?:[\t ][^\n]*)?(?:\n|$))"
    ),
    "nextBulletRegex": _cached_indent_regex(
        lambda indent: re.compile(
            r"^ {0," + str(indent) + r"}(?:[*+-]|\d{1,9}[.)])((?:[ \t][^\n]*)?(?:\n|$))"
        )
    ),
    "hrRegex": _cached_indent_regex(
        lambda indent: re.compile(
            r"^ {0," + str(indent) + r"}((?:- *){3,}|(?:_ *){3,}|(?:\* *){3,})(?:\n+|$)"
        )
    ),
    "fencesBeginRegex": _cached_indent_regex(
        lambda indent: re.compile(r"^ {0," + str(indent) + r"}(?:```|~~~)")
    ),
    "headingBeginRegex": _cached_indent_regex(
        lambda indent: re.compile(r"^ {0," + str(indent) + r"}#")
    ),
    "htmlBeginRegex": _cached_indent_regex(
        lambda indent: re.compile(
            r"^ {0," + str(indent) + r"}<(?:[a-z].*>|!--)", re.I
        )
    ),
    "blockquoteBeginRegex": _cached_indent_regex(
        lambda indent: re.compile(r"^ {0," + str(indent) + r"}>")
    ),
}

# ---------------------------------------------------------------------------
# Block grammar
# ---------------------------------------------------------------------------

_newline = r"^(?:[ \t]*(?:\n|$))+"
_block_code = r"^((?: {4}| {0,3}\t)[^\n]+(?:\n(?:[ \t]*(?:\n|$))*)?)+"
_fences = (
    r"^ {0,3}(`{3,}(?=[^`\n]*(?:\n|$))|~{3,})([^\n]*)(?:\n|$)"
    r"(?:|([\s\S]*?)(?:\n|$))(?: {0,3}\1[~`]* *(?=\n|$)|$)"
)
_hr = r"^ {0,3}((?:-[\t ]*){3,}|(?:_[ \t]*){3,}|(?:\*[ \t]*){3,})(?:\n+|$)"
_heading = r"^ {0,3}(#{1,6})(?=\s|$)(.*)(?:\n+|$)"
_bullet = r" {0,3}(?:[*+-]|\d{1,9}[.)])"

_lheading_core = (
    r"^(?!bull |blockCode|fences|blockquote|heading|html|table)"
    r"((?:.|\n(?!\s*?\n|bull |blockCode|fences|blockquote|heading|html|table))+?)"
    r"\n {0,3}(=+|-+) *(?:\n+|$)"
)


def _make_lheading(with_table):
    e = (
        _edit(_lheading_core)
        .replace(re.compile("bull"), _bullet)
        .replace(re.compile("blockCode"), r"(?: {4}| {0,3}\t)")
        .replace(re.compile("fences"), r" {0,3}(?:`{3,}|~{3,})")
        .replace(re.compile("blockquote"), r" {0,3}>")
        .replace(re.compile("heading"), r" {0,3}#{1,6}(?:\s|$)")
        .replace(re.compile("html"), r" {0,3}<[^\n>]+>\n")
    )
    if with_table:
        e.replace("table", r" {0,3}\|?(?:[:\- ]*\|)+[\:\- ]*\n")
    else:
        e.replace("|table", "")
    return e.get_regex()


_lheading = _make_lheading(False)
_lheading_gfm = _make_lheading(True)

_paragraph_core = r"^([^\n]+(?:\n(?!hr|heading|lheading|blockquote|fences|list|html|table|[ \t]+\n)[^\n]+)*)"
_block_text = r"^[^\n]+"
_block_label = r"(?!\s*\])(?:\\[\s\S]|[^\[\]\\])+"

_def = (
    _edit(
        r"^ {0,3}\[(label)\]: *(?:\n[ \t]*)?([^<\s][^\s]*|<.*?>)"
        r"(?:(?: +(?:\n[ \t]*)?| *\n[ \t]*)(title))? *(?:\n+|$)"
    )
    .replace("label", _block_label)
    .replace("title", r"(?:\"(?:\\\"?|[^\"\\])*\"|'[^'\n]*(?:\n[^'\n]+)*\n?'|\([^()]*\))")
    .get_regex()
)

_list = _edit(r"^(bull)([ \t][^\n]*?)?(?:\n|$)").replace(re.compile("bull"), _bullet).get_regex()

_tag_names = (
    "address|article|aside|base|basefont|blockquote|body|caption"
    "|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption"
    "|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe"
    "|legend|li|link|main|menu|menuitem|meta|nav|noframes|ol|optgroup|option"
    "|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title"
    "|tr|track|ul"
)
_comment = r"<!--(?:-?>|[\s\S]*?(?:-->|$))"

_html_block = (
    _edit(
        r"^ {0,3}(?:"
        r"<(script|pre|style|textarea)[\s>][\s\S]*?(?:</\1>[^\n]*\n*|$)"
        r"|comment[^\n]*(\n+|$)"
        r"|<\?[\s\S]*?(?:\?>[^\n]*\n*|$)"
        r"|<![A-Z][\s\S]*?(?:>[^\n]*\n*|$)"
        r"|<!\[CDATA\[[\s\S]*?(?:\]\]>[^\n]*\n*|$)"
        r"|</?(tag)(?: +|\n|/?>)[\s\S]*?(?:(?:\n[ \t]*)+\n|$)"
        r"|<(?!script|pre|style|textarea)([a-z][\w-]*)(?:attribute)*? */?>(?=[ \t]*(?:\n|$))[\s\S]*?(?:(?:\n[ \t]*)+\n|$)"
        r"|</(?!script|pre|style|textarea)[a-z][\w-]*\s*>(?=[ \t]*(?:\n|$))[\s\S]*?(?:(?:\n[ \t]*)+\n|$)"
        r")",
        "i",
    )
    .replace("comment", _comment)
    .replace("tag", _tag_names)
    .replace(
        "attribute",
        r" +[a-zA-Z:_][\w.:-]*(?: *= *\"[^\"\n]*\"| *= *'[^'\n]*'| *= *[^\s\"'=<>`]+)?",
    )
    .get_regex()
)


def _create_paragraph(list_interrupt):
    return (
        _edit(_paragraph_core)
        .replace("hr", _hr)
        .replace("heading", r" {0,3}#{1,6}(?:\s|$)")
        .replace("|lheading", "")
        .replace("|table", "")
        .replace("blockquote", r" {0,3}>")
        .replace("fences", r" {0,3}(?:`{3,}(?=[^`\n]*(?:\n|$))|~~~)[^\n]*(?:\n|$)")
        .replace("list", list_interrupt)
        .replace("html", r"</?(?:tag)(?: +|\n|/?>)|<(?:script|pre|style|textarea|!--)")
        .replace("tag", _tag_names)
        .get_regex()
    )


_paragraph = _create_paragraph(r" {0,3}(?:[*+-]|1[.)])[ \t]+[^ \t\n]")
_blockquote_paragraph = _create_paragraph(r" {0,3}(?:[*+-]|\d{1,9}[.)])(?:[ \t]|\n|$)")

_blockquote = (
    _edit(r"^( {0,3}> ?(paragraph|[^\n]*)(?:\n|$))+")
    .replace("paragraph", _blockquote_paragraph)
    .get_regex()
)

_gfm_table = (
    _edit(
        r"^ *([^\n ].*)\n"
        r" {0,3}((?:\| *)?:?-+:? *(?:\| *:?-+:? *)*(?:\| *)?)"
        r"(?:\n((?:(?! *\n|hr|heading|blockquote|code|fences|list|html).*(?:\n|$))*)\n*|$)"
    )
    .replace("hr", _hr)
    .replace("heading", r" {0,3}#{1,6}(?:\s|$)")
    .replace("blockquote", r" {0,3}>")
    .replace("code", r"(?: {4}| {0,3}\t)[^\n]")
    .replace("fences", r" {0,3}(?:`{3,}(?=[^`\n]*(?:\n|$))|~~~)[^\n]*(?:\n|$)")
    .replace("list", r" {0,3}(?:[*+-]|1[.)])[ \t]")
    .replace("html", r"</?(?:tag)(?: +|\n|/?>)|<(?:script|pre|style|textarea|!--)")
    .replace("tag", _tag_names)
    .get_regex()
)

_gfm_paragraph = (
    _edit(_paragraph_core)
    .replace("hr", _hr)
    .replace("heading", r" {0,3}#{1,6}(?:\s|$)")
    .replace("|lheading", "")
    .replace("table", _gfm_table)
    .replace("blockquote", r" {0,3}>")
    .replace("fences", r" {0,3}(?:`{3,}(?=[^`\n]*(?:\n|$))|~~~)[^\n]*(?:\n|$)")
    .replace("list", r" {0,3}(?:[*+-]|1[.)])[ \t]+[^ \t\n]")
    .replace("html", r"</?(?:tag)(?: +|\n|/?>)|<(?:script|pre|style|textarea|!--)")
    .replace("tag", _tag_names)
    .get_regex()
)


def _compile(src, opt=""):
    flags = 0
    if "i" in opt:
        flags |= re.I
    if "m" in opt:
        flags |= re.M
    if "s" in opt:
        flags |= re.S
    return re.compile(src, flags)


block_normal = {
    "blockquote": _blockquote,
    "code": _compile(_block_code),
    "def": _def,
    "fences": _compile(_fences),
    "heading": _compile(_heading),
    "hr": _compile(_hr),
    "html": _html_block,
    "lheading": _lheading,
    "list": _list,
    "newline": _compile(_newline),
    "paragraph": _paragraph,
    "table": noop_test,
    "text": _compile(_block_text),
}

block_gfm = dict(block_normal)
block_gfm.update(
    {"lheading": _lheading_gfm, "table": _gfm_table, "paragraph": _gfm_paragraph}
)

_pedantic_html = (
    _edit(
        r"^ *(?:comment *(?:\n|\s*$)"
        r"|<(tag)[\s\S]+?</\1> *(?:\n{2,}|\s*$)"
        r"|<tag(?:\"[^\"]*\"|'[^']*'|\s[^'\"/>\s]*)*?/?> *(?:\n{2,}|\s*$))"
    )
    .replace("comment", _comment)
    .replace(
        re.compile("tag"),
        r"(?!(?:a|em|strong|small|s|cite|q|dfn|abbr|data|time|code|var|samp|kbd|sub"
        r"|sup|i|b|u|mark|ruby|rt|rp|bdi|bdo|span|br|wbr|ins|del|img)\b)\w+(?!:|[^\w\s@]*@)\b",
    )
    .get_regex()
)

block_pedantic = dict(block_normal)
block_pedantic.update(
    {
        "html": _pedantic_html,
        "def": _compile(r"^ *\[([^\]]+)\]: *<?([^\s>]+)>?(?: +([\"(][^\n]+[\")]))? *(?:\n+|$)"),
        "heading": _compile(r"^(#{1,6})(.*)(?:\n+|$)"),
        "fences": noop_test,
        "lheading": _compile(r"^(.+?)\n {0,3}(=+|-+) *(?:\n+|$)"),
        "paragraph": (
            _edit(_paragraph_core)
            .replace("hr", _hr)
            .replace("heading", r" *#{1,6} *[^\n]")
            .replace("lheading", _lheading.pattern)
            .replace("|table", "")
            .replace("blockquote", r" {0,3}>")
            .replace("|fences", "")
            .replace("|list", "")
            .replace("|html", "")
            .replace("|tag", "")
            .get_regex()
        ),
    }
)

# ---------------------------------------------------------------------------
# Inline grammar
# ---------------------------------------------------------------------------

_punctuation = "[" + _UP + _US + "]"
_punctuation_or_space = "[" + r"\s" + _UP + _US + "]"
_not_punctuation_or_space = "[^" + r"\s" + _UP + _US + "]"
_open_quote = "[" + _UPI + _UPS + "\"']"
_punct_gfm = "(?!~)[" + _UP + _US + "]"
_punct_or_space_gfm = "(?!~)[" + r"\s" + _UP + _US + "]"
_not_punct_or_space_gfm = "(?:[^" + r"\s" + _UP + _US + "]|~)"

_escape = r"^\\([!\"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])"
_inline_code = r"^(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)"
_br = r"^( {2,}|\\)\n(?!\s*$)"
_inline_text = r"^(`+|[^`])(?:(?= {2,}\n)|[\s\S]*?(?:(?=[\\<!\[`*_]|\b_|$)|[^ ](?= {2,}\n)))"

_punctuation_re = _edit(r"^((?![*_])punctSpace)", "").replace(
    re.compile("punctSpace"), _punctuation_or_space
).get_regex()

# blockSkip: use marked's no-lookbehind fallback branch
_block_skip = (
    _edit(r"link|precode-code|html", "")
    .replace(
        "link",
        r"\[(?:[^\[\]`]|(?P<a>`+)[^`]+(?P=a)(?!`))*?\]\((?:\\[\s\S]|[^\\()]|\((?:\\[\s\S]|[^\\()])*\))*\)",
    )
    .replace("precode-", r"(^^|[^`])")
    .replace("code", r"(?P<b>`+)[^`]+(?P=b)(?!`)")
    .replace("html", r"<(?! )[^<>]*?>")
    .get_regex()
)

_em_strong_l_delim_core = (
    r"^(?:\*+(?:((?!\*)punct)|([^\s*]))?)|^_+(?:((?!_)punct)|([^\s_]))?"
)
_em_strong_l_delim = _edit(_em_strong_l_delim_core, "").replace(
    re.compile("punct"), _punctuation
).get_regex()
_em_strong_l_delim_gfm = _edit(_em_strong_l_delim_core, "").replace(
    re.compile("punct"), _punct_gfm
).get_regex()

_em_strong_r_delim_ast_core = (
    r"^[^_*]*?__[^_*]*?\*[^_*]*?(?=__)"
    r"|[^*]+(?=[^*])"
    r"|(?!\*)punct(\*+)(?=[\s]|$)"
    r"|notPunctSpace(\*+)(?!\*)(?=punctSpace|$)"
    r"|(?!\*)punctSpace(\*+)(?=notPunctSpace)"
    r"|[\s](\*+)(?!\*)(?=punct)"
    r"|(?!\*)punct(\*+)(?!\*)(?=punct)"
    r"|notPunctSpace(\*+)(?=notPunctSpace)"
)


def _build_r_delim(core, not_ps, ps, punct):
    return (
        _edit(core, "")
        .replace(re.compile("notPunctSpace"), not_ps)
        .replace(re.compile("punctSpace"), ps)
        .replace(re.compile("punct"), punct)
        .get_regex()
    )


_em_strong_r_delim_ast = _build_r_delim(
    _em_strong_r_delim_ast_core, _not_punctuation_or_space, _punctuation_or_space, _punctuation
)
_em_strong_r_delim_ast_gfm = _build_r_delim(
    _em_strong_r_delim_ast_core, _not_punct_or_space_gfm, _punct_or_space_gfm, _punct_gfm
)

_em_strong_r_delim_und_core = (
    r"^[^_*]*?\*\*[^_*]*?_[^_*]*?(?=\*\*)"
    r"|[^_]+(?=[^_])"
    r"|(?!_)punct(_+)(?=[\s]|$)"
    r"|notPunctSpace(_+)(?!_)(?=punctSpace|$)"
    r"|(?!_)punctSpace(_+)(?=notPunctSpace)"
    r"|[\s](_+)(?!_)(?=punct)"
    r"|(?!_)punct(_+)(?!_)(?=punct)"
)
_em_strong_r_delim_und = _build_r_delim(
    _em_strong_r_delim_und_core, _not_punctuation_or_space, _punctuation_or_space, _punctuation
)

_del_l_delim = _edit(r"^~~?(?:((?!~)punct)|[^\s~])", "").replace(
    re.compile("punct"), _punctuation
).get_regex()

_del_r_delim_core = (
    r"^[^~]+(?=[^~])"
    r"|(?!~)punct(~~?)(?=[\s]|$)"
    r"|notPunctSpace(~~?)(?!~)(?=punctSpace|$)"
    r"|(?!~)punctSpace(~~?)(?=notPunctSpace)"
    r"|[\s](~~?)(?!~)(?=punct)"
    r"|(?!~)punct(~~?)(?!~)(?=punct)"
    r"|notPunctSpace(~~?)(?=notPunctSpace)"
)
_del_r_delim = _build_r_delim(
    _del_r_delim_core, _not_punctuation_or_space, _punctuation_or_space, _punctuation
)

_any_punctuation = _edit(r"\\(punct)", "").replace(
    re.compile("punct"), _punctuation
).get_regex()

_autolink = (
    _edit(r"^<(scheme:[^\s\x00-\x1f<>]*|email)>")
    .replace("scheme", r"[a-zA-Z][a-zA-Z0-9+.-]{1,31}")
    .replace(
        "email",
        r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+(@)[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+(?![-_])",
    )
    .get_regex()
)

_inline_comment = _edit(_comment).replace("(?:-->|$)", "-->").get_regex()

_tag = (
    _edit(
        r"^comment"
        r"|^</[a-zA-Z][\w:-]*\s*>"
        r"|^<[a-zA-Z][\w-]*(?:attribute)*?\s*/?>"
        r"|^<\?[\s\S]*?\?>"
        r"|^<![a-zA-Z]+\s[\s\S]*?>"
        r"|^<!\[CDATA\[[\s\S]*?\]\]>"
    )
    .replace("comment", _inline_comment.pattern)
    .replace(
        "attribute",
        r"\s+[a-zA-Z:_][\w.:-]*(?:\s*=\s*\"[^\"]*\"|\s*=\s*'[^']*'|\s*=\s*[^\s\"'=<>`]+)?",
    )
    .get_regex()
)

_inline_label = (
    r"(?:\[(?:\\[\s\S]|[^\[\]\\])*\]|\\[\s\S]|`+(?!`)[^`]*?`+(?!`)|``+(?=\])|[^\[\]\\`])*?"
)

_link = (
    _edit(r"^!?\[(label)\]\(\s*(href)(?:(?:[ \t]+(?:\n[ \t]*)?|\n[ \t]*)(title))?\s*\)")
    .replace("label", _inline_label)
    .replace("href", r"<(?:\\.|[^\n<>\\])+>|[^ \t\n\x00-\x1f]+|(?=\))")
    .replace("title", r"\"(?:\\\"?|[^\"\\])*\"|'(?:\\'?|[^'\\])*'|\((?:\\\)?|[^)\\])*\)")
    .get_regex()
)

_reflink = (
    _edit(r"^!?\[(label)\]\[(ref)\]")
    .replace("label", _inline_label)
    .replace("ref", _block_label)
    .get_regex()
)

_nolink = (
    _edit(r"^!?\[(ref)\](?:\[\])?").replace("ref", _block_label).get_regex()
)

_reflink_search = (
    _edit(r"reflink|nolink(?!\()")
    .replace("reflink", _reflink.pattern)
    .replace("nolink", _nolink.pattern)
    .get_regex()
)

_ci_protocol = r"[hH][tT][tT][pP][sS]?|[fF][tT][pP]"

inline_normal = {
    "_backpedal": noop_test,
    "anyPunctuation": _any_punctuation,
    "autolink": _autolink,
    "blockSkip": _block_skip,
    "br": _compile(_br),
    "code": _compile(_inline_code),
    "del": noop_test,
    "delLDelim": noop_test,
    "delRDelim": noop_test,
    "emStrongLDelim": _em_strong_l_delim,
    "emStrongRDelimAst": _em_strong_r_delim_ast,
    "emStrongRDelimUnd": _em_strong_r_delim_und,
    "escape": _compile(_escape),
    "link": _link,
    "nolink": _nolink,
    "punctuation": _punctuation_re,
    "reflink": _reflink,
    "reflinkSearch": _reflink_search,
    "tag": _tag,
    "text": _compile(_inline_text),
    "url": noop_test,
}

inline_pedantic = dict(inline_normal)
inline_pedantic.update(
    {
        "link": _edit(r"^!?\[(label)\]\((.*?)\)").replace("label", _inline_label).get_regex(),
        "reflink": _edit(r"^!?\[(label)\]\s*\[([^\]]*)\]")
        .replace("label", _inline_label)
        .get_regex(),
    }
)

_gfm_url = (
    _edit(r"^((?:protocol)://|www\.)(?:[a-zA-Z0-9\-]+\.?)+[^\s<]*|^email")
    .replace("protocol", _ci_protocol)
    .replace(
        "email",
        r"[A-Za-z0-9._+-]+(@)[a-zA-Z0-9-_]+(?:\.[a-zA-Z0-9-_]*[a-zA-Z0-9])+(?![-_])",
    )
    .get_regex()
)

_gfm_text = (
    _edit(
        r"^(`+|~+|[^`~])(?:(?=[`~])|(?= {2,}\n)|(?=[a-zA-Z0-9.!#$%&'*+/=?_`{|}~-]+@)"
        r"|[\s\S]*?(?:(?=[\\<!\[`*~_]|\b_|protocol://|www\.|$)|[^ ](?= {2,}\n)"
        r"|[^a-zA-Z0-9.!#$%&'*+/=?_`{|}~-](?=[a-zA-Z0-9.!#$%&'*+/=?_`{|}~-]+@)))"
    )
    .replace("protocol", _ci_protocol)
    .get_regex()
)

inline_gfm = dict(inline_normal)
inline_gfm.update(
    {
        "emStrongRDelimAst": _em_strong_r_delim_ast_gfm,
        "emStrongLDelim": _em_strong_l_delim_gfm,
        "delLDelim": _del_l_delim,
        "delRDelim": _del_r_delim,
        "url": _gfm_url,
        "_backpedal": _compile(
            r"(?:[^?!.,:;*_'\"~()&]+|\([^)]*\)|&(?![a-zA-Z0-9]+;$)|[?!.,:;*_'\"~)]+(?!$))+"
        ),
        "del": _compile(
            r"^(~~?)(?=[^\s~])((?:\\[\s\S]|[^\\])*?(?:\\[\s\S]|[^\s~\\]))\1(?=[^~]|$)"
        ),
        "text": _gfm_text,
    }
)

inline_breaks = dict(inline_gfm)
inline_breaks.update(
    {
        "br": _edit(_br).replace("{2,}", "*").get_regex(),
        "text": _edit(inline_gfm["text"].pattern)
        .replace(r"\b_", r"\b_| {2,}\n")
        .replace(re.compile(r"\{2,\}"), "*")
        .get_regex(),
    }
)

block = {"normal": block_normal, "gfm": block_gfm, "pedantic": block_pedantic}
inline = {
    "normal": inline_normal,
    "gfm": inline_gfm,
    "breaks": inline_breaks,
    "pedantic": inline_pedantic,
}
