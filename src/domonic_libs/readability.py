"""Extract the readable article from a domonic document.

This module is a Python port of Mozilla's Readability.js.  It deliberately
keeps the same scoring model and broadly the same private method names so that
upstream fixes can be compared and ported without having to rediscover the
algorithm.

Readability.js copyright (c) 2010 Arc90 Inc. and Mozilla contributors.
Licensed under the Apache License, Version 2.0.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urljoin

from domonic.javascript import Math, String
from domonic.webapi.url import URL
from domonic.dom import Document, Element, Node


class Readability:
    """Mozilla Readability's article extraction algorithm for domonic DOMs."""

    FLAG_STRIP_UNLIKELYS = 0x1
    FLAG_WEIGHT_CLASSES = 0x2
    FLAG_CLEAN_CONDITIONALLY = 0x4
    ELEMENT_NODE = 1
    TEXT_NODE = 3

    DEFAULT_MAX_ELEMS_TO_PARSE = 0
    DEFAULT_N_TOP_CANDIDATES = 5
    DEFAULT_CHAR_THRESHOLD = 500
    DEFAULT_TAGS_TO_SCORE = ("SECTION", "H2", "H3", "H4", "H5", "H6", "P", "TD", "PRE")

    UNLIKELY_ROLES = {
        "menu", "menubar", "complementary", "navigation", "alert",
        "alertdialog", "dialog",
    }
    DIV_TO_P_ELEMS = {"BLOCKQUOTE", "DL", "DIV", "IMG", "OL", "P", "PRE", "TABLE", "UL"}
    ALTER_TO_DIV_EXCEPTIONS = {"DIV", "ARTICLE", "SECTION", "P", "OL", "UL"}
    BLOCK_ELEMS = {
        "ARTICLE", "ASIDE", "BLOCKQUOTE", "BR", "DD", "DIV", "DL", "DT",
        "FIGCAPTION", "FIGURE", "FOOTER", "H1", "H2", "H3", "H4", "H5",
        "H6", "HEADER", "HR", "LI", "MAIN", "NAV", "OL", "P", "PRE",
        "SECTION", "TABLE", "TD", "TH", "TR", "UL",
    }
    PRESENTATIONAL_ATTRIBUTES = {
        "align", "background", "bgcolor", "border", "cellpadding",
        "cellspacing", "frame", "hspace", "rules", "style", "valign", "vspace",
    }
    DEPRECATED_SIZE_ATTRIBUTE_ELEMS = {"TABLE", "TH", "TD", "HR", "PRE"}
    PHRASING_ELEMS = {
        "ABBR", "AUDIO", "B", "BDO", "BR", "BUTTON", "CITE", "CODE", "DATA",
        "DATALIST", "DFN", "EM", "EMBED", "I", "IMG", "INPUT", "KBD", "LABEL",
        "MARK", "MATH", "METER", "NOSCRIPT", "OBJECT", "OUTPUT", "PROGRESS",
        "Q", "RUBY", "SAMP", "SCRIPT", "SELECT", "SMALL", "SPAN", "STRONG",
        "SUB", "SUP", "TEXTAREA", "TIME", "VAR", "WBR",
    }
    CLASSES_TO_PRESERVE = {"page"}
    HTML_ESCAPE_MAP = {
        "lt": "<",
        "gt": ">",
        "amp": "&",
        "quot": '"',
        "apos": "'",
    }

    REGEXPS = {
        "unlikelyCandidates": re.compile(
            r"-ad-|ai2html|banner|breadcrumbs|combx|comment|community|cover-wrap|"
            r"disqus|extra|footer|gdpr|header|legends|menu|related|remark|replies|"
            r"rss|shoutbox|sidebar|skyscraper|social|sponsor|supplemental|ad-break|"
            r"agegate|pagination|pager|popup|yom-remote", re.I
        ),
        "okMaybeItsACandidate": re.compile(r"and|article|body|column|content|main|mathjax|shadow", re.I),
        "positive": re.compile(r"article|body|content|entry|hentry|h-entry|main|page|pagination|post|text|blog|story", re.I),
        "negative": re.compile(r"-ad-|hidden|^hid$| hid$| hid |^hid |banner|combx|comment|com-|contact|footer|gdpr|masthead|media|meta|outbrain|promo|related|scroll|share|shoutbox|sidebar|skyscraper|sponsor|shopping|tags|widget", re.I),
        "extraneous": re.compile(r"print|archive|comment|discuss|e[-]?mail|share|reply|all|login|sign|single|utility", re.I),
        "byline": re.compile(r"byline|author|dateline|writtenby|p-author", re.I),
        "videos": re.compile(r"//(www\.)?((dailymotion|youtube|youtube-nocookie|player\.vimeo|v\.qq|bilibili|live\.bilibili)\.com|(archive|upload\.wikimedia)\.org|player\.twitch\.tv)", re.I),
        "shareElements": re.compile(r"(\b|_)(share|sharedaddy)(\b|_)", re.I),
        "nextLink": re.compile(r"(next|weiter|continue|>([^\|]|$)|»([^\|]|$))", re.I),
        "prevLink": re.compile(r"(prev|earl|old|new|<|«)", re.I),
        "tokenize": re.compile(r"\W+"),
        "normalize": re.compile(r"\s{2,}"),
        "whitespace": re.compile(r"^\s*$"),
        "hasContent": re.compile(r"\S"),
        "hashUrl": re.compile(r"^#.+"),
        "srcsetUrl": re.compile(r"(\S+)(\s+[\d.]+[xw])?(\s*(?:,|$))"),
        "b64DataUrl": re.compile(r"^data:\s*([^\s;,]+)\s*;\s*base64\s*,", re.I),
        "commas": re.compile("\u002c|\u060c|\ufe50|\ufe10|\ufe11|\u2e41|\u2e34|\u2e32|\uff0c"),
        "jsonLdArticleTypes": re.compile(
            r"^Article|AdvertiserContentArticle|NewsArticle|AnalysisNewsArticle|"
            r"AskPublicNewsArticle|BackgroundNewsArticle|OpinionNewsArticle|"
            r"ReportageNewsArticle|ReviewNewsArticle|Report|SatiricalArticle|"
            r"ScholarlyArticle|MedicalScholarlyArticle|SocialMediaPosting|"
            r"BlogPosting|LiveBlogPosting|DiscussionForumPosting|TechArticle|APIReference$"
        ),
        "adWords": re.compile(r"^(ad(vertising|vertisement)?|pub(licité)?|werb(ung)?|广告|Реклама|Anuncio)$", re.I),
        "loadingWords": re.compile(r"^((loading|正在加载|Загрузка|chargement|cargando)(…|\.\.\.)?)$", re.I),
    }

    def __init__(self, doc: Node, options: dict[str, Any] | None = None, **kwargs: Any):
        # Parser adapters may return DocumentFragment for a complete document
        # containing a doctype, so accept all DOM nodes that expose traversal.
        if not isinstance(doc, Node) or not hasattr(doc, "getElementsByTagName"):
            raise TypeError("First argument to Readability must be a domonic document or DOM node")
        opts = dict(options or {})
        opts.update(kwargs)
        self._doc = doc
        base_nodes = list(doc.getElementsByTagName("base"))
        document_url = getattr(doc, "URL", "") or ""
        raw_base_uri = self._attr(base_nodes[0], "href") if base_nodes else ""
        self._base_uri = (
            (urljoin(document_url, raw_base_uri) if raw_base_uri else "")
            or getattr(doc, "baseURI", "")
            or document_url
            or ""
        )
        self._article_title: str | None = None
        self._article_byline: str | None = None
        self._article_dir: str | None = None
        self._article_site_name: str | None = None
        self._article_uri: str = document_url
        self._attempts: list[dict[str, Any]] = []
        self._metadata: dict[str, Any] = {}
        self._article_image: str | None = None
        self._debug = bool(self._option(opts, "debug", default=False))
        self._max_elems_to_parse = int(self._option(opts, "maxElemsToParse", "max_elems_to_parse", default=0))
        self._nb_top_candidates = int(self._option(opts, "nbTopCandidates", "nb_top_candidates", default=5))
        self._char_threshold = int(self._option(opts, "charThreshold", "char_threshold", default=500))
        preserve = self._option(opts, "classesToPreserve", "classes_to_preserve", default=[]) or []
        self._classes_to_preserve = self.CLASSES_TO_PRESERVE | set(preserve)
        self._keep_classes = bool(self._option(opts, "keepClasses", "keep_classes", default=False))
        self._disable_json_ld = bool(self._option(opts, "disableJSONLD", "disable_json_ld", default=False))
        self._allowed_video_regex = self._option(opts, "allowedVideoRegex", "allowed_video_regex", default=None) or self.REGEXPS["videos"]
        self._link_density_modifier = float(self._option(opts, "linkDensityModifier", "link_density_modifier", default=0))
        self._serializer = self._option(opts, "serializer", default=None) or (lambda el: el.innerHTML)
        self._flags = self.FLAG_STRIP_UNLIKELYS | self.FLAG_WEIGHT_CLASSES | self.FLAG_CLEAN_CONDITIONALLY

    @staticmethod
    def _option(options: dict[str, Any], *names: str, default: Any = None) -> Any:
        for name in names:
            if name in options:
                return options[name]
        return default

    def _log(self, *values: Any) -> None:
        if self._debug:
            print("Reader: (Readability)", *values)

    @staticmethod
    def _tag(node: Any) -> str:
        return str(getattr(node, "tagName", getattr(node, "nodeName", "")) or "").upper()

    @staticmethod
    def _elements(node: Any) -> list[Element]:
        return [child for child in getattr(node, "args", ()) if isinstance(child, Element)]

    @staticmethod
    def _text(node: Any) -> str:
        return (getattr(node, "textContent", None) or "").strip()

    @staticmethod
    def _attr(node: Any, name: str) -> str:
        value = node.getAttribute(name) if hasattr(node, "getAttribute") else None
        return "" if value is None else str(value)

    @staticmethod
    def _attribute_items(node: Any) -> list[tuple[str, str]]:
        attributes = getattr(node, "attributes", None)
        if attributes is None or not hasattr(attributes, "keys"):
            return []
        return [(name, node.getAttribute(name) or "") for name in attributes.keys()]

    @staticmethod
    def _dom_value(node: Any, name: str) -> Any:
        value = getattr(node, name, None)
        return value() if callable(value) else value

    def _child_nodes(self, node: Any) -> list[Any]:
        args = list(getattr(node, "args", ()))
        if args:
            return args
        children = self._dom_value(node, "childNodes")
        if children is not None:
            return list(children)
        return args

    def _element_children(self, node: Any) -> list[Element]:
        args = [child for child in getattr(node, "args", ()) if isinstance(child, Element)]
        if args:
            return args
        children = self._dom_value(node, "children")
        if children is not None:
            return [child for child in children if isinstance(child, Element)]
        return args

    def _first_child(self, node: Any) -> Any:
        args = list(getattr(node, "args", ()))
        if args:
            return args[0]
        return self._dom_value(node, "firstChild")

    def _last_child(self, node: Any) -> Any:
        args = list(getattr(node, "args", ()))
        if args:
            return args[-1]
        return self._dom_value(node, "lastChild")

    def _first_element_child(self, node: Any) -> Element | None:
        for child in getattr(node, "args", ()):
            if isinstance(child, Element):
                return child
        child = self._dom_value(node, "firstElementChild")
        return child if isinstance(child, Element) else None

    def _next_sibling(self, node: Any) -> Any:
        parent = getattr(node, "parentNode", None)
        siblings = list(getattr(parent, "args", ())) if parent is not None else []
        for index, sibling in enumerate(siblings):
            if sibling is node:
                return siblings[index + 1] if index + 1 < len(siblings) else None
        return self._dom_value(node, "nextSibling")

    def _next_element_sibling(self, node: Any) -> Element | None:
        parent = getattr(node, "parentNode", None)
        siblings = list(getattr(parent, "args", ())) if parent is not None else []
        seen = False
        for sibling in siblings:
            if sibling is node:
                seen = True
                continue
            if seen and isinstance(sibling, Element):
                return sibling
        sibling = self._dom_value(node, "nextElementSibling")
        return sibling if isinstance(sibling, Element) else None

    def _previous_element_sibling(self, node: Any) -> Element | None:
        parent = getattr(node, "parentNode", None)
        siblings = list(getattr(parent, "args", ())) if parent is not None else []
        previous = None
        for sibling in siblings:
            if sibling is node:
                return previous
            if isinstance(sibling, Element):
                previous = sibling
        sibling = self._dom_value(node, "previousElementSibling")
        return sibling if isinstance(sibling, Element) else None

    def _get_all_nodes_with_tag(self, node: Any, tag_names: Iterable[str]) -> list[Element]:
        result: list[Element] = []
        seen: set[int] = set()
        for tag in tag_names:
            for item in node.getElementsByTagName(tag):
                if id(item) not in seen:
                    seen.add(id(item))
                    result.append(item)
        return result

    def _is_url(self, value: str) -> bool:
        try:
            URL(value)
            return True
        except Exception:
            return False

    def _remove_nodes(self, nodes: Iterable[Element], predicate: Callable[[Element], bool] | None = None) -> None:
        for node in reversed(list(nodes)):
            if node.parentNode is not None and (predicate is None or predicate(node)):
                node.parentNode.removeChild(node)

    def _replace_node_tags(self, nodes: Iterable[Element], tag_name: str) -> None:
        for node in list(nodes):
            self._set_node_tag(node, tag_name)

    def _for_each_node(self, nodes: Iterable[Any], fn: Callable[..., Any]) -> None:
        for index, node in enumerate(list(nodes)):
            fn(node, index)

    def _find_node(self, nodes: Iterable[Any], fn: Callable[[Any], bool]) -> Any:
        for node in nodes:
            if fn(node):
                return node
        return None

    def _some_node(self, nodes: Iterable[Any], fn: Callable[..., bool]) -> bool:
        for index, node in enumerate(list(nodes)):
            if fn(node, index):
                return True
        return False

    def _every_node(self, nodes: Iterable[Any], fn: Callable[..., bool]) -> bool:
        for index, node in enumerate(list(nodes)):
            if not fn(node, index):
                return False
        return True

    def _get_inner_text(self, element: Any, normalize_spaces: bool = True) -> str:
        # domonic's textContent currently becomes None when any descendant
        # (for example an empty img) has no text. Readability must retain the
        # surrounding prose, so collect text from the tree defensively.
        def collect(node: Any) -> str:
            if isinstance(node, str):
                return node
            node_value = getattr(node, "nodeValue", None)
            if not isinstance(node, Element) and node_value is not None:
                return str(node_value)
            text = "".join(collect(child) for child in getattr(node, "args", ()))
            if isinstance(node, Element) and self._tag(node) in self.BLOCK_ELEMS:
                return f"\n{text}\n"
            return text

        text = str(String(collect(element)).trim())
        return self._normalize_spaces(text) if normalize_spaces else text

    def _normalize_spaces(self, value: str) -> str:
        return self.REGEXPS["normalize"].sub(" ", value).strip()

    def _get_char_count(self, element: Any, separator: str = ",") -> int:
        return len(self._get_inner_text(element).split(separator)) - 1

    def _get_link_density(self, element: Element) -> float:
        text_length = len(self._get_inner_text(element))
        if not text_length:
            return 0.0
        link_length = 0.0
        for link in element.getElementsByTagName("a"):
            coefficient = 0.3 if self._attr(link, "href").startswith("#") else 1.0
            link_length += len(self._get_inner_text(link)) * coefficient
        return link_length / text_length

    def _get_class_weight(self, element: Element) -> int:
        if not self._flag_is_active(self.FLAG_WEIGHT_CLASSES):
            return 0
        weight = 0
        for value in (self._attr(element, "class"), self._attr(element, "id")):
            if self.REGEXPS["negative"].search(value):
                weight -= 25
            if self.REGEXPS["positive"].search(value):
                weight += 25
        return weight

    def _initialize_node(self, node: Element) -> None:
        score = 0.0
        tag = self._tag(node)
        if tag == "DIV":
            score += 5
        elif tag in {"PRE", "TD", "BLOCKQUOTE"}:
            score += 3
        elif tag in {"ADDRESS", "OL", "UL", "DL", "DD", "DT", "LI", "FORM"}:
            score -= 3
        elif tag in {"H1", "H2", "H3", "H4", "H5", "H6", "TH"}:
            score -= 5
        node._readability = {"contentScore": score + self._get_class_weight(node)}

    def _prep_document(self) -> None:
        self._remove_nodes(self._get_all_nodes_with_tag(self._doc, ("style",)))
        body_nodes = list(self._doc.getElementsByTagName("body"))
        self._replace_brs(body_nodes[0] if body_nodes else self._doc)
        self._replace_node_tags(self._get_all_nodes_with_tag(self._doc, ("font",)), "span")

    def _remove_scripts(self, doc: Element) -> None:
        self._remove_nodes(self._get_all_nodes_with_tag(doc, ("script", "noscript")))

    def _wrap_readability_page(self, article: Element) -> None:
        children = list(getattr(article, "args", ()))
        if len(children) == 1 and isinstance(children[0], Element) and self._attr(children[0], "id") == "readability-page-1":
            return
        page = self._create_element("div")
        page.setAttribute("id", "readability-page-1")
        page.setAttribute("class", "page")
        for child in children:
            self._append_reparented(page, child)
        article.args = ()
        article.appendChild(page)

    def _create_element(self, tag: str) -> Element:
        creator = getattr(self._doc, "createElement", None)
        if creator:
            return creator(tag)
        return Document.createElement(tag)

    def _copy_attributes(self, source: Element, target: Element) -> None:
        attributes = getattr(source, "attributes", None)
        keys = attributes.keys() if attributes is not None and hasattr(attributes, "keys") else []
        for name in keys:
            value = self._attr(source, name)
            if value:
                target.setAttribute(name, value)

    def _append_reparented(self, parent: Element, child: Any) -> None:
        if isinstance(child, Element):
            child.parentNode = parent
        parent.appendChild(child)

    def _set_node_tag(self, node: Element, tag: str) -> Element:
        replacement = self._create_element(tag)
        self._copy_attributes(node, replacement)
        readability = getattr(node, "_readability", None)
        if readability is not None:
            replacement._readability = readability
        for child in list(getattr(node, "args", ())):
            self._append_reparented(replacement, child)
        if node.parentNode:
            node.parentNode.replaceChild(replacement, node)
        return replacement

    def _next_node(self, node: Any) -> Any:
        next_node = node
        while next_node and not isinstance(next_node, Element) and self.REGEXPS["whitespace"].search(self._get_inner_text(next_node, False)):
            next_node = self._next_sibling(next_node)
        return next_node

    def _get_next_node(self, node: Any, ignore_self_and_kids: bool = False) -> Any:
        if not ignore_self_and_kids:
            child = self._first_element_child(node)
            if child is not None:
                return child
        sibling = self._next_element_sibling(node)
        if sibling is not None:
            return sibling
        parent = getattr(node, "parentNode", None)
        while parent is not None and self._next_element_sibling(parent) is None:
            parent = getattr(parent, "parentNode", None)
        return self._next_element_sibling(parent) if parent is not None else None

    def _remove_and_get_next(self, node: Element) -> Any:
        next_node = self._get_next_node(node, True)
        if node.parentNode:
            node.parentNode.removeChild(node)
        return next_node

    def _has_single_tag_inside_element(self, element: Element, tag: str) -> bool:
        children = self._element_children(element)
        if len(children) != 1 or self._tag(children[0]) != tag.upper():
            return False
        for child in getattr(element, "args", ()):
            if not isinstance(child, Element) and getattr(child, "nodeValue", None) is not None:
                if self.REGEXPS["hasContent"].search(str(getattr(child, "nodeValue"))):
                    return False
        return True

    def _is_element_without_content(self, node: Any) -> bool:
        if not isinstance(node, Element):
            return False
        children = self._element_children(node)
        if self._get_inner_text(node):
            return False
        if not children:
            return True
        empty_children = len(node.getElementsByTagName("br")) + len(node.getElementsByTagName("hr"))
        return len(children) == empty_children

    def _is_whitespace(self, node: Any) -> bool:
        if isinstance(node, str):
            return not node.strip()
        node_value = getattr(node, "nodeValue", None)
        if not isinstance(node, Element) and node_value is not None:
            return not str(node_value).strip()
        return isinstance(node, Element) and self._tag(node) == "BR"

    def _has_real_content(self, nodes: Iterable[Any]) -> bool:
        for node in nodes:
            if isinstance(node, str) and node.strip():
                return True
            node_value = getattr(node, "nodeValue", None)
            if not isinstance(node, Element) and node_value is not None and str(node_value).strip():
                return True
            if isinstance(node, Element):
                if self._tag(node) in {"IMG", "VIDEO", "AUDIO", "IFRAME", "OBJECT", "EMBED"}:
                    return True
                if self._get_inner_text(node):
                    return True
        return False

    def _paragraph_from(self, nodes: Iterable[Any]) -> Element:
        paragraph = self._create_element("p")
        for node in nodes:
            self._append_reparented(paragraph, node)
        return paragraph

    def _has_ancestor_tag(
        self,
        node: Element,
        tag_name: str,
        max_depth: int = 3,
        filter_fn: Callable[[Element], bool] | None = None,
    ) -> bool:
        tag_name = tag_name.upper()
        depth = 0
        parent = node.parentNode
        while isinstance(parent, Element):
            if max_depth > 0 and depth > max_depth:
                return False
            if self._tag(parent) == tag_name and (filter_fn is None or filter_fn(parent)):
                return True
            parent = parent.parentNode
            depth += 1
        return False

    def _replace_brs(self, node: Any) -> None:
        if not isinstance(node, Element):
            for child in self._elements(node):
                self._replace_brs(child)
            return

        children = list(getattr(node, "args", ()))
        if not any(isinstance(child, Element) and self._tag(child) == "BR" for child in children):
            for child in self._elements(node):
                self._replace_brs(child)
            return

        rebuilt: list[Any] = []
        paragraph_nodes: list[Any] = []
        br_run = 0
        saw_separator = False

        def flush_paragraph() -> None:
            if self._has_real_content(paragraph_nodes):
                paragraph = self._paragraph_from(paragraph_nodes)
                paragraph.parentNode = node
                rebuilt.append(paragraph)
            paragraph_nodes.clear()

        for child in children:
            is_br = isinstance(child, Element) and self._tag(child) == "BR"
            if is_br:
                br_run += 1
                continue

            if br_run >= 2:
                saw_separator = True
                flush_paragraph()
            elif br_run == 1:
                paragraph_nodes.append(self._create_element("br"))
            br_run = 0
            paragraph_nodes.append(child)

        if br_run >= 2:
            saw_separator = True
            flush_paragraph()
        elif br_run == 1:
            paragraph_nodes.append(self._create_element("br"))

        if saw_separator:
            flush_paragraph()
            node.args = tuple(rebuilt)
            for child in self._elements(node):
                child.parentNode = node
                self._replace_brs(child)
            if self._tag(node) == "P":
                self._set_node_tag(node, "div")
        else:
            for child in self._elements(node):
                self._replace_brs(child)

    def _is_phrasing_or_text(self, node: Any) -> bool:
        if isinstance(node, str):
            return True
        if not isinstance(node, Element) and getattr(node, "nodeValue", None) is not None:
            return True
        if not isinstance(node, Element):
            return False
        if self._tag(node) in self.PHRASING_ELEMS:
            return True
        return self._tag(node) in {"A", "DEL", "INS"} and self._every_node(
            self._child_nodes(node),
            lambda child, _index=0: self._is_phrasing_or_text(child),
        )

    def _is_phrasing_content(self, node: Any) -> bool:
        return self._is_phrasing_or_text(node)

    def _replace_misused_divs(self, node: Any) -> None:
        for div in reversed(list(node.getElementsByTagName("div"))):
            if not self._has_child_block_element(div):
                paragraph = self._create_element("p")
                self._copy_attributes(div, paragraph)
                for child in list(getattr(div, "args", ())):
                    self._append_reparented(paragraph, child)
                if div.parentNode:
                    div.parentNode.replaceChild(paragraph, div)
                continue

            rebuilt: list[Any] = []
            paragraph_nodes: list[Any] = []

            def flush_paragraph() -> None:
                if self._has_real_content(paragraph_nodes):
                    paragraph = self._paragraph_from(paragraph_nodes)
                    paragraph.parentNode = div
                    rebuilt.append(paragraph)
                paragraph_nodes.clear()

            for child in list(getattr(div, "args", ())):
                if self._is_phrasing_or_text(child):
                    paragraph_nodes.append(child)
                    continue
                flush_paragraph()
                if isinstance(child, Element):
                    child.parentNode = div
                rebuilt.append(child)

            flush_paragraph()

            if rebuilt and rebuilt != list(getattr(div, "args", ())):
                div.args = tuple(rebuilt)

    def _wrap_phrasing_content(self, element: Element) -> None:
        rebuilt: list[Any] = []
        paragraph_nodes: list[Any] = []

        def flush_paragraph() -> None:
            while paragraph_nodes and self._is_whitespace(paragraph_nodes[0]):
                paragraph_nodes.pop(0)
            while paragraph_nodes and self._is_whitespace(paragraph_nodes[-1]):
                paragraph_nodes.pop()
            if paragraph_nodes:
                paragraph = self._paragraph_from(paragraph_nodes)
                paragraph.parentNode = element
                rebuilt.append(paragraph)
            paragraph_nodes.clear()

        for child in list(getattr(element, "args", ())):
            if self._is_phrasing_content(child):
                paragraph_nodes.append(child)
                continue
            flush_paragraph()
            if isinstance(child, Element):
                child.parentNode = element
            rebuilt.append(child)
        flush_paragraph()
        if rebuilt:
            element.args = tuple(rebuilt)

    def _is_probably_visible(self, node: Element) -> bool:
        style = self._attr(node, "style").replace(" ", "").lower()
        return not (
            "display:none" in style
            or "visibility:hidden" in style
            or node.hasAttribute("hidden")
            or self._attr(node, "aria-hidden") == "true"
        )

    def _is_valid_byline(self, node: Element, match: str) -> bool:
        if self._article_byline or not match or len(match) >= 100:
            return False
        rel = self._attr(node, "rel")
        itemprop = self._attr(node, "itemprop")
        return bool(self.REGEXPS["byline"].search(match) or rel == "author" or "author" in itemprop)

    def _clean_byline(self, value: str) -> str:
        value = self._normalize_spaces(value)
        value = re.sub(r"^(by|from|written by)\s+", "", value, flags=re.I)
        value = re.sub(r"\s*[|\-\u2013\u2014]\s*$", "", value)
        return value.strip()

    def _clean_title(self, title: str) -> str:
        title = self._normalize_spaces(title)
        original = title
        if re.search(r"\s[|\-\u2013\u2014\\/>»]\s", title):
            parts = re.split(r"\s[|\-\u2013\u2014\\/>»]\s", title)
            title = " | ".join(parts[:-1]).strip()
            if len(title.split()) < 3:
                title = re.sub(r"^[^|\-\u2013\u2014\\/>»]*[|\-\u2013\u2014\\/>»]", "", original).strip()
        elif ": " in title:
            candidate = title.split(": ", 1)[1].strip()
            if len(candidate.split()) >= 3:
                title = candidate
        return self._normalize_spaces(title or original)

    def _grab_article(self, page: Element) -> Element | None:
        elements_to_score: list[Element] = []
        should_remove_title_header = True
        html_nodes = list(page.getElementsByTagName("html"))
        node: Any = html_nodes[0] if html_nodes else self._get_next_node(page)
        while node is not None:
            if not self._is_probably_visible(node):
                node = self._remove_and_get_next(node)
                continue
            match = f"{self._attr(node, 'class')} {self._attr(node, 'id')}"
            if self._attr(node, "aria-modal") == "true" and self._attr(node, "role") == "dialog":
                node = self._remove_and_get_next(node)
                continue
            if not self._article_byline and not self._metadata.get("byline") and self._is_valid_byline(node, match):
                itemprop_name_node = self._find_node(
                    node.getElementsByTagName("*"),
                    lambda descendant: "name" in self._attr(descendant, "itemprop"),
                )
                self._article_byline = self._clean_byline(self._get_inner_text(itemprop_name_node or node))
                node = self._remove_and_get_next(node)
                continue
            if should_remove_title_header and self._header_duplicates_title(node):
                should_remove_title_header = False
                node = self._remove_and_get_next(node)
                continue
            if self._flag_is_active(self.FLAG_STRIP_UNLIKELYS):
                role = self._attr(node, "role").lower()
                unlikely = self.REGEXPS["unlikelyCandidates"].search(match)
                allowed = self.REGEXPS["okMaybeItsACandidate"].search(match)
                in_protected_ancestor = self._has_ancestor_tag(node, "table") or self._has_ancestor_tag(node, "code")
                if ((unlikely and not allowed and not in_protected_ancestor) or role in self.UNLIKELY_ROLES):
                    if self._tag(node) not in {"BODY", "A"} and node.parentNode:
                        node = self._remove_and_get_next(node)
                        continue
            tag = self._tag(node)
            if tag in {"DIV", "SECTION", "HEADER", "H1", "H2", "H3", "H4", "H5", "H6"} and self._is_element_without_content(node):
                node = self._remove_and_get_next(node)
                continue
            if tag in self.DEFAULT_TAGS_TO_SCORE:
                elements_to_score.append(node)
            if tag == "DIV":
                self._wrap_phrasing_content(node)
                if self._has_single_tag_inside_element(node, "p") and self._get_link_density(node) < 0.25:
                    child = self._element_children(node)[0]
                    self._copy_attributes(node, child)
                    if node.parentNode:
                        node.parentNode.replaceChild(child, node)
                    node = child
                    elements_to_score.append(node)
                elif not self._has_child_block_element(node):
                    node = self._set_node_tag(node, "p")
                    elements_to_score.append(node)
            node = self._get_next_node(node)

        candidates: list[Element] = []
        for element in elements_to_score:
            text = self._get_inner_text(element)
            if len(text) < 25:
                continue
            ancestors = self._get_node_ancestors(element, 5)
            if not ancestors:
                continue
            content_score = 1 + self._get_char_count(element)
            content_score += min(Math.floor(len(text) / 100), 3)
            for level, ancestor in enumerate(ancestors):
                if not hasattr(ancestor, "_readability"):
                    self._initialize_node(ancestor)
                    candidates.append(ancestor)
                divisor = 1 if level == 0 else 2 if level == 1 else level * 3
                ancestor._readability["contentScore"] += content_score / divisor

        top_candidates: list[Element] = []
        for candidate in candidates:
            score = candidate._readability["contentScore"]
            score *= 1 - self._get_link_density(candidate)
            candidate._readability["contentScore"] = score
            inserted = False
            for index, current in enumerate(top_candidates):
                if score > current._readability["contentScore"]:
                    top_candidates.insert(index, candidate)
                    inserted = True
                    break
            if not inserted:
                top_candidates.append(candidate)
            top_candidates = top_candidates[: self._nb_top_candidates]

        top_candidate = top_candidates[0] if top_candidates else None
        if top_candidate is None or self._tag(top_candidate) == "BODY":
            body = page.querySelector("body") if hasattr(page, "querySelector") else None
            source = body or page
            top_candidate = self._create_element("div")
            top_candidate.setAttribute("id", "readability-page-1")
            for child in list(getattr(source, "args", ())):
                top_candidate.appendChild(child)
            self._initialize_node(top_candidate)
        elif top_candidate is not None:
            alternative_ancestor_lists = []
            for candidate in top_candidates[1:]:
                top_score = top_candidate._readability["contentScore"] or 1
                if candidate._readability["contentScore"] / top_score >= 0.75:
                    alternative_ancestor_lists.append(self._get_node_ancestors(candidate))
            if len(alternative_ancestor_lists) >= 3:
                parent = top_candidate.parentNode
                while isinstance(parent, Element) and self._tag(parent) != "BODY":
                    containing_lists = sum(1 for ancestors in alternative_ancestor_lists if parent in ancestors)
                    if containing_lists >= 3:
                        top_candidate = parent
                        break
                    parent = parent.parentNode
            if not hasattr(top_candidate, "_readability"):
                self._initialize_node(top_candidate)

            parent = top_candidate.parentNode
            last_score = top_candidate._readability["contentScore"]
            score_threshold = last_score / 3
            while isinstance(parent, Element) and self._tag(parent) != "BODY":
                if not hasattr(parent, "_readability"):
                    parent = parent.parentNode
                    continue
                parent_score = parent._readability["contentScore"]
                if parent_score < score_threshold:
                    break
                if parent_score > last_score:
                    top_candidate = parent
                    break
                last_score = parent_score
                parent = parent.parentNode

            parent = top_candidate.parentNode
            while (
                isinstance(parent, Element)
                and self._tag(parent) != "BODY"
                and len(self._element_children(parent)) == 1
            ):
                top_candidate = parent
                parent = top_candidate.parentNode
            if not hasattr(top_candidate, "_readability"):
                self._initialize_node(top_candidate)

        article = self._create_element("div")
        article.setAttribute("id", "readability-content")
        sibling_score_threshold = max(10, top_candidate._readability["contentScore"] * 0.2)
        parent = top_candidate.parentNode
        siblings = list(getattr(parent, "args", ())) if parent is not None else [top_candidate]
        for sibling in siblings:
            if not isinstance(sibling, Element):
                continue
            append = sibling is top_candidate
            bonus = 0.0
            if self._attr(sibling, "class") and self._attr(sibling, "class") == self._attr(top_candidate, "class"):
                bonus = top_candidate._readability["contentScore"] * 0.2
            score = getattr(sibling, "_readability", {}).get("contentScore", 0) + bonus
            if score >= sibling_score_threshold:
                append = True
            if self._tag(sibling) == "P":
                link_density = self._get_link_density(sibling)
                text = self._get_inner_text(sibling)
                if len(text) > 80 and link_density < 0.25:
                    append = True
                elif len(text) <= 80 and link_density == 0 and re.search(r"\.(\s|$)", text):
                    append = True
            if append:
                article.appendChild(sibling)
        ancestors = [node for node in (parent, top_candidate) if isinstance(node, Element)]
        if isinstance(parent, Element):
            ancestors.extend(self._get_node_ancestors(parent))
        for ancestor in ancestors:
            article_dir = self._attr(ancestor, "dir")
            if article_dir:
                self._article_dir = article_dir
                break
        return article

    def _get_node_ancestors(self, node: Element, max_depth: int = 0) -> list[Element]:
        ancestors: list[Element] = []
        parent = node.parentNode
        while isinstance(parent, Element) and (not max_depth or len(ancestors) < max_depth):
            ancestors.append(parent)
            parent = parent.parentNode
        return ancestors

    def _has_child_block_element(self, element: Element) -> bool:
        for child in self._child_nodes(element):
            if not isinstance(child, Element):
                continue
            if self._tag(child) in self.DIV_TO_P_ELEMS or self._has_child_block_element(child):
                return True
        return False

    def _clean(self, element: Element, tag: str) -> None:
        is_embed = tag.lower() in {"object", "embed", "iframe"}

        def should_remove(node: Element) -> bool:
            if is_embed:
                for _name, value in self._attribute_items(node):
                    if self._allowed_video_regex.search(value):
                        return False
                if self._tag(node) == "OBJECT" and self._allowed_video_regex.search(str(node.innerHTML)):
                    return False
            return True

        self._remove_nodes(element.getElementsByTagName(tag), should_remove)

    def _clean_matched_nodes(self, element: Element, predicate: Callable[[Element, str], bool]) -> None:
        nodes = list(element.getElementsByTagName("*"))
        self._remove_nodes(nodes, lambda node: predicate(node, f"{self._attr(node, 'class')} {self._attr(node, 'id')}"))

    def _clean_conditionally(self, element: Element, tag: str) -> None:
        if not self._flag_is_active(self.FLAG_CLEAN_CONDITIONALLY):
            return
        for node in reversed(list(element.getElementsByTagName(tag))):
            is_data_table = lambda table: bool(getattr(table, "_readability_data_table", False))
            is_list = tag.lower() in {"ul", "ol"}
            if not is_list:
                list_length = sum(self._get_inner_text(item).__len__() for item in self._get_all_nodes_with_tag(node, ("ul", "ol")))
                node_length = len(self._get_inner_text(node))
                is_list = node_length > 0 and list_length / node_length > 0.9

            if tag.lower() == "table" and is_data_table(node):
                continue
            if self._has_ancestor_tag(node, "table", -1, is_data_table):
                continue
            if self._has_ancestor_tag(node, "code"):
                continue
            if any(getattr(table, "_readability_data_table", False) for table in node.getElementsByTagName("table")):
                continue
            weight = self._get_class_weight(node)
            content_score = getattr(node, "_readability", {}).get("contentScore", 0)
            if weight + content_score < 0:
                if node.parentNode:
                    node.parentNode.removeChild(node)
                continue
            text = self._get_inner_text(node)
            if self.REGEXPS["commas"].search(text) and self._get_char_count(node, ",") >= 10:
                continue
            counts = {name: len(node.getElementsByTagName(name)) for name in ("p", "img", "li", "input", "embed", "object", "iframe")}
            heading_density = self._get_text_density(node, ("h1", "h2", "h3", "h4", "h5", "h6"))
            embed_count = 0
            for embed in self._get_all_nodes_with_tag(node, ("object", "embed", "iframe")):
                if any(self._allowed_video_regex.search(value) for _name, value in self._attribute_items(embed)):
                    continue
                if self._tag(embed) == "OBJECT" and self._allowed_video_regex.search(str(embed.innerHTML)):
                    continue
                embed_count += 1
            link_density = self._get_link_density(node)
            textish_tags = ("span", "li", "td", *self.DIV_TO_P_ELEMS)
            text_density = self._get_text_density(node, textish_tags)
            is_figure_child = self._has_ancestor_tag(node, "figure")
            remove = (
                self.REGEXPS["adWords"].search(text)
                or self.REGEXPS["loadingWords"].search(text)
                or (not is_figure_child and counts["img"] > 1 and counts["p"] / max(counts["img"], 1) < 0.5)
                or (not is_list and counts["li"] - 100 > counts["p"])
                or counts["input"] > Math.floor(counts["p"] / 3)
                or (
                    not is_list
                    and not is_figure_child
                    and heading_density < 0.9
                    and len(text) < 25
                    and (counts["img"] == 0 or counts["img"] > 2)
                    and link_density > 0
                )
                or (not is_list and weight < 25 and link_density > 0.2 + self._link_density_modifier)
                or (weight >= 25 and link_density > 0.5 + self._link_density_modifier)
                or ((embed_count == 1 and len(text) < 75) or embed_count > 1)
                or (counts["img"] == 0 and text_density == 0)
            )
            if is_list and remove:
                children = self._element_children(node)
                if all(len(self._element_children(child)) <= 1 for child in children):
                    li_count = len(node.getElementsByTagName("li"))
                    if counts["img"] == li_count:
                        remove = False
            if remove and node.parentNode:
                node.parentNode.removeChild(node)

    def _prep_article(self, article: Element) -> None:
        self._clean_styles(article)
        self._mark_data_tables(article)
        self._fix_lazy_images(article)
        for tag in ("form", "fieldset"):
            self._clean_conditionally(article, tag)
        for tag in ("object", "embed", "footer", "link", "aside"):
            self._clean(article, tag)
        share_threshold = self.DEFAULT_CHAR_THRESHOLD
        self._clean_matched_nodes(
            article,
            lambda node, match: bool(self.REGEXPS["shareElements"].search(match))
            and len(self._get_inner_text(node)) < share_threshold,
        )
        for top_candidate in self._element_children(article):
            self._clean_matched_nodes(
                top_candidate,
                lambda node, match: bool(self.REGEXPS["shareElements"].search(match))
                and len(self._get_inner_text(node)) < share_threshold,
            )
        for tag in ("iframe", "input", "textarea", "select", "button"):
            self._clean(article, tag)
        self._clean_headers(article)
        for tag in ("table", "ul", "div"):
            self._clean_conditionally(article, tag)
        self._replace_node_tags(self._get_all_nodes_with_tag(article, ("h1",)), "h2")
        self._remove_nodes(
            self._get_all_nodes_with_tag(article, ("p",)),
            lambda paragraph: not self._get_all_nodes_with_tag(paragraph, ("img", "embed", "object", "iframe"))
            and not self._get_inner_text(paragraph, False),
        )
        self._remove_nodes(
            self._get_all_nodes_with_tag(article, ("br",)),
            lambda br: self._tag(self._next_node(self._next_sibling(br))) == "P",
        )
        for table in list(article.getElementsByTagName("table")):
            tbody = self._first_element_child(table) if self._has_single_tag_inside_element(table, "tbody") else table
            if not isinstance(tbody, Element) or not self._has_single_tag_inside_element(tbody, "tr"):
                continue
            row = self._first_element_child(tbody)
            if not isinstance(row, Element) or not self._has_single_tag_inside_element(row, "td"):
                continue
            cell = self._first_element_child(row)
            if not isinstance(cell, Element):
                continue
            tag = "p" if self._every_node(self._child_nodes(cell), lambda child, _index=0: self._is_phrasing_content(child)) else "div"
            cell = self._set_node_tag(cell, tag)
            if table.parentNode:
                table.parentNode.replaceChild(cell, table)
        self._remove_empty_nodes(article)
        self._simplify_nested_elements(article)

    def _text_similarity(self, left: str, right: str) -> float:
        tokens_a = [token for token in self.REGEXPS["tokenize"].split(left.lower()) if token]
        tokens_b = [token for token in self.REGEXPS["tokenize"].split(right.lower()) if token]
        if not tokens_a or not tokens_b:
            return 0.0
        unique_b = [token for token in tokens_b if token not in tokens_a]
        denominator = len(" ".join(tokens_b))
        if not denominator:
            return 0.0
        return 1 - len(" ".join(unique_b)) / denominator

    def _header_duplicates_title(self, heading: Element) -> bool:
        if self._tag(heading) not in {"H1", "H2"} or not self._article_title:
            return False
        return self._text_similarity(self._get_inner_text(heading), self._article_title) > 0.75

    def _clean_headers(self, article: Element) -> None:
        for heading in list(self._get_all_nodes_with_tag(article, ("h1", "h2", "h3", "h4", "h5", "h6"))):
            text = self._get_inner_text(heading)
            class_weight = self._get_class_weight(heading)
            link_density = self._get_link_density(heading)
            too_short = len(text) < 5 and self._tag(heading) not in {"H1", "H2"}
            if self._header_duplicates_title(heading) or class_weight < 0 or link_density > 0.33 or too_short:
                if heading.parentNode:
                    heading.parentNode.removeChild(heading)

    def _remove_empty_nodes(self, article: Element) -> None:
        media_tags = ("img", "embed", "object", "iframe", "video", "audio", "source")
        for tag in ("p", "div", "section"):
            for node in reversed(list(article.getElementsByTagName(tag))):
                if node is article:
                    continue
                has_media = any(node.getElementsByTagName(media_tag) for media_tag in media_tags)
                if not has_media and not self._get_inner_text(node):
                    if node.parentNode:
                        node.parentNode.removeChild(node)

    def _simplify_nested_elements(self, article: Element) -> None:
        for node in reversed(list(self._get_all_nodes_with_tag(article, ("div", "section")))):
            if node is article or self._attr(node, "id") == "readability-content":
                continue
            children = [child for child in getattr(node, "args", ()) if isinstance(child, Element)]
            has_loose_text = any(
                (isinstance(child, str) and child.strip())
                or (
                    not isinstance(child, Element)
                    and getattr(child, "nodeValue", None) is not None
                    and str(getattr(child, "nodeValue")).strip()
                )
                for child in getattr(node, "args", ())
            )
            if has_loose_text or len(children) != 1:
                continue
            child = children[0]
            if self._tag(child) not in {"DIV", "SECTION", "ARTICLE", "P"}:
                continue
            if node.parentNode:
                node.parentNode.replaceChild(child, node)

    def _get_row_and_column_count(self, table: Element) -> dict[str, int]:
        rows = 0
        columns = 0
        for tr in table.getElementsByTagName("tr"):
            rowspan = self._attr(tr, "rowspan")
            rows += int(rowspan) if rowspan.isdigit() else 1
            columns_in_this_row = 0
            for cell in tr.getElementsByTagName("td"):
                colspan = self._attr(cell, "colspan")
                columns_in_this_row += int(colspan) if colspan.isdigit() else 1
            columns = Math.max(columns, columns_in_this_row)
        return {"rows": rows, "columns": columns}

    def _mark_data_tables(self, article: Element) -> None:
        for table in article.getElementsByTagName("table"):
            role = self._attr(table, "role").lower()
            if role == "presentation":
                table._readability_data_table = False
                continue
            if self._attr(table, "datatable") == "0":
                table._readability_data_table = False
                continue
            if self._attr(table, "summary"):
                table._readability_data_table = True
                continue
            caption = list(table.getElementsByTagName("caption"))
            if caption and getattr(caption[0], "args", ()):
                table._readability_data_table = True
                continue
            if any(table.getElementsByTagName(tag) for tag in ("col", "colgroup", "tfoot", "thead", "th")):
                table._readability_data_table = True
                continue
            if table.getElementsByTagName("table"):
                table._readability_data_table = False
                continue
            size = self._get_row_and_column_count(table)
            if size["columns"] == 1 or size["rows"] == 1:
                table._readability_data_table = False
                continue
            if size["rows"] >= 10 or size["columns"] > 4:
                table._readability_data_table = True
                continue
            table._readability_data_table = size["rows"] * size["columns"] > 10

    def _get_text_density(self, element: Element, tags: Iterable[str]) -> float:
        text_length = len(self._get_inner_text(element))
        if text_length == 0:
            return 0.0
        children_length = sum(len(self._get_inner_text(child)) for child in self._get_all_nodes_with_tag(element, tags))
        return children_length / text_length

    def _clean_styles(self, element: Element) -> None:
        if not element or self._tag(element) == "SVG":
            return
        for attr in self.PRESENTATIONAL_ATTRIBUTES:
            element.removeAttribute(attr)
        if self._tag(element) in self.DEPRECATED_SIZE_ATTRIBUTE_ELEMS:
            element.removeAttribute("width")
            element.removeAttribute("height")
        child = self._first_element_child(element)
        while child is not None:
            self._clean_styles(child)
            child = self._next_element_sibling(child)

    def _clean_classes(self, node: Element) -> None:
        classes = self._attr(node, "class").split()
        kept = [name for name in classes if name in self._classes_to_preserve]
        if kept:
            node.setAttribute("class", " ".join(kept))
        else:
            node.removeAttribute("class")
        child = self._first_element_child(node)
        while child is not None:
            self._clean_classes(child)
            child = self._next_element_sibling(child)

    def _fix_relative_uris(self, article: Element) -> None:
        base = self._base_uri
        document_uri = getattr(self._doc, "documentURI", "") or getattr(self._doc, "URL", "") or ""

        def absolute_uri(uri: str) -> str:
            if base == document_uri and uri.startswith("#"):
                return uri
            try:
                return urljoin(base, uri)
            except Exception:
                return uri

        for link in article.getElementsByTagName("a"):
            href = self._attr(link, "href")
            if href.lower().startswith("javascript:"):
                self._replace_javascript_link(link)
            elif href:
                link.setAttribute("href", absolute_uri(href))
        for tag in ("img", "picture", "figure", "video", "audio", "source"):
            for media in article.getElementsByTagName(tag):
                for attr in ("src", "poster"):
                    value = self._attr(media, attr)
                    if value:
                        media.setAttribute(attr, absolute_uri(value))
                srcset = self._attr(media, "srcset")
                if srcset:
                    media.setAttribute("srcset", self._fix_srcset(srcset))

    def _fix_srcset(self, value: str) -> str:
        candidates = []
        for candidate in value.split(","):
            parts = candidate.strip().split()
            if not parts:
                continue
            parts[0] = urljoin(self._base_uri, parts[0])
            candidates.append(" ".join(parts))
        return ", ".join(candidates)

    def _replace_javascript_link(self, link: Element) -> None:
        parent = link.parentNode
        if parent is None:
            link.removeAttribute("href")
            return
        children = list(getattr(link, "args", ()))
        if len(children) == 1 and not isinstance(children[0], Element):
            text = self._doc.createTextNode(self._get_inner_text(link)) if hasattr(self._doc, "createTextNode") else self._get_inner_text(link)
            parent.replaceChild(text, link)
            return
        container = self._create_element("span")
        for child in children:
            self._append_reparented(container, child)
        parent.replaceChild(container, link)

    def _post_process_content(self, article: Element) -> None:
        self._unwrap_noscript_images(article)
        self._fix_lazy_images(article)
        self._remove_image_placeholders(article)
        self._fix_relative_uris(article)
        self._simplify_nested_elements(article)
        if not self._keep_classes:
            self._clean_classes(article)

    def _replace_noscript_images(self, article: Element) -> None:
        self._unwrap_noscript_images(article)

    def _is_single_image(self, node: Element) -> bool:
        current: Element | None = node
        while current is not None:
            if self._tag(current) == "IMG":
                return True
            children = self._element_children(current)
            if len(children) != 1 or self._get_inner_text(current).strip():
                return False
            current = children[0]
        return False

    def _unwrap_noscript_images(self, article: Element) -> None:
        has_image_reference = re.compile(r"\.(jpg|jpeg|png|webp)", re.I)
        for image in list(article.getElementsByTagName("img")):
            keep = False
            for name, value in self._attribute_items(image):
                if name in {"src", "srcset", "data-src", "data-srcset"} or has_image_reference.search(value):
                    keep = True
                    break
            if not keep and image.parentNode:
                image.parentNode.removeChild(image)

        for noscript in list(article.getElementsByTagName("noscript")):
            parent = noscript.parentNode
            if parent is None or not self._is_single_image(noscript):
                continue

            images = list(noscript.getElementsByTagName("img"))
            if not images:
                continue
            new_image = images[0]
            previous = self._previous_element_sibling(noscript)
            if previous is not None and self._is_single_image(previous):
                previous_images = [previous] if self._tag(previous) == "IMG" else list(previous.getElementsByTagName("img"))
                previous_image = previous_images[0] if previous_images else None
                if previous_image is not None:
                    for name, value in self._attribute_items(previous_image):
                        if not value:
                            continue
                        if value.startswith("data:"):
                            continue
                        if name in {"src", "srcset"} or has_image_reference.search(value):
                            if self._attr(new_image, name) == value:
                                continue
                            attr_name = f"data-old-{name}" if self._attr(new_image, name) else name
                            new_image.setAttribute(attr_name, value)
                parent.replaceChild(new_image, previous)
                if noscript.parentNode:
                    noscript.parentNode.removeChild(noscript)

    def _fix_lazy_images(self, article: Element) -> None:
        image_url = re.compile(r"^\s*\S+\.(jpg|jpeg|png|webp)\S*\s*$", re.I)
        srcset_url = re.compile(r"\.(jpg|jpeg|png|webp)\s+\d", re.I)
        for element in self._get_all_nodes_with_tag(article, ("img", "picture", "figure")):
            src = self._attr(element, "src")
            srcset = self._attr(element, "srcset")
            data_uri = self.REGEXPS["b64DataUrl"].search(src)
            if data_uri and data_uri.group(1).lower() != "image/svg+xml":
                src_could_be_removed = any(
                    name != "src" and re.search(r"\.(jpg|jpeg|png|webp)", value, re.I)
                    for name, value in self._attribute_items(element)
                )
                if src_could_be_removed:
                    b64length = len(src) - len(data_uri.group(0))
                    if b64length < 133:
                        element.removeAttribute("src")
                        src = ""
            class_name = self._attr(element, "class").lower()
            if (src or (srcset and srcset != "null")) and "lazy" not in class_name:
                continue
            for name, value in self._attribute_items(element):
                if name in {"src", "srcset", "alt"}:
                    continue
                copy_to = None
                if srcset_url.search(value):
                    copy_to = "srcset"
                elif image_url.search(value):
                    copy_to = "src"
                if not copy_to:
                    continue
                tag = self._tag(element)
                if tag in {"IMG", "PICTURE"}:
                    element.setAttribute(copy_to, value)
                elif tag == "FIGURE" and not self._get_all_nodes_with_tag(element, ("img", "picture")):
                    image = self._create_element("img")
                    image.setAttribute(copy_to, value)
                    element.appendChild(image)

    def _remove_image_placeholders(self, article: Element) -> None:
        for image in list(article.getElementsByTagName("img")):
            src = self._attr(image, "src")
            if not src.startswith("data:"):
                continue
            has_replacement = any(
                self._attr(image, attr)
                for attr in (
                    "data-src",
                    "data-lazy-src",
                    "data-original",
                    "data-url",
                    "data-srcset",
                    "data-lazy-srcset",
                    "data-original-set",
                )
            )
            if not has_replacement and image.parentNode:
                image.parentNode.removeChild(image)

    def _get_article_title(self) -> str:
        title = ""
        title_nodes = self._doc.getElementsByTagName("title")
        if title_nodes:
            title = self._get_inner_text(title_nodes[0])
        if not title:
            headings = list(self._doc.getElementsByTagName("h1"))
            title = self._get_inner_text(headings[0]) if headings else ""
        title = self._clean_title(title)
        if len(title.split()) <= 4:
            h1s = list(self._doc.getElementsByTagName("h1"))
            if len(h1s) == 1:
                heading = self._get_inner_text(h1s[0])
                if heading:
                    title = heading
        return self._normalize_spaces(title)

    def _unescape_html_entities(self, value: str | None) -> str | None:
        if not value:
            return value
        return html.unescape(value)

    def _get_json_ld(self) -> dict[str, Any]:
        if self._disable_json_ld:
            return {}
        for script in self._doc.getElementsByTagName("script"):
            if self._attr(script, "type").lower() != "application/ld+json":
                continue
            try:
                content = re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", self._get_inner_text(script, False))
                data = json.loads(content)
            except (TypeError, ValueError):
                continue
            items = self._json_ld_items(data)
            for item in items:
                context = item.get("@context") if isinstance(item, dict) else None
                schema_context = (
                    (isinstance(context, str) and re.match(r"^https?://schema\.org/?$", context))
                    or (
                        isinstance(context, dict)
                        and isinstance(context.get("@vocab"), str)
                        and re.match(r"^https?://schema\.org/?$", context["@vocab"])
                    )
                )
                if not schema_context:
                    continue
                kinds = item.get("@type", []) if isinstance(item, dict) else []
                kinds = [kinds] if isinstance(kinds, str) else kinds
                normalized_kinds = {str(kind).rstrip("/").rsplit("/", 1)[-1] for kind in kinds}
                if any(self.REGEXPS["jsonLdArticleTypes"].search(kind) for kind in normalized_kinds):
                    html_title = self._get_article_title()
                    name = item.get("name")
                    headline = item.get("headline")
                    if isinstance(name, str) and isinstance(headline, str) and name != headline:
                        title = headline if self._text_similarity(headline, html_title) > 0.75 and self._text_similarity(name, html_title) <= 0.75 else name
                    elif isinstance(name, str):
                        title = name.strip()
                    elif isinstance(headline, str):
                        title = headline.strip()
                    else:
                        title = None
                    author = item.get("author")
                    if isinstance(author, list):
                        byline = ", ".join(
                            str(a.get("name", "")).strip() if isinstance(a, dict) else str(a).strip()
                            for a in author
                            if a
                        )
                    elif isinstance(author, dict):
                        byline = author.get("name", "").strip()
                    else:
                        byline = author
                    publisher = item.get("publisher")
                    image = item.get("image")
                    if isinstance(image, list):
                        image = image[0] if image else None
                    if isinstance(image, dict):
                        image = image.get("url")
                    return {
                        "title": title,
                        "byline": byline,
                        "excerpt": item.get("description"),
                        "siteName": publisher.get("name") if isinstance(publisher, dict) else None,
                        "publishedTime": item.get("datePublished"),
                        "modifiedTime": item.get("dateModified"),
                        "image": image,
                    }
        return {}

    def _get_jsonld(self) -> dict[str, Any]:
        return self._get_json_ld()

    def _json_ld_items(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for value in data for item in self._json_ld_items(value)]
        if not isinstance(data, dict):
            return []
        items = [data]
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                if not isinstance(item, dict):
                    continue
                if "@context" not in item and "@context" in data:
                    item = dict(item)
                    item["@context"] = data["@context"]
                items.append(item)
        return items

    def _get_article_metadata(self, json_ld: dict[str, Any]) -> dict[str, Any]:
        values: dict[str, str] = {}
        for meta in self._doc.getElementsByTagName("meta"):
            key = (
                self._attr(meta, "property")
                or self._attr(meta, "name")
                or self._attr(meta, "itemprop")
            ).lower()
            content = self._attr(meta, "content")
            if key and content:
                values[key] = content
        links: dict[str, str] = {}
        for link in self._doc.getElementsByTagName("link"):
            rel = " ".join(self._attr(link, "rel").lower().split())
            href = self._attr(link, "href")
            if rel and href:
                links[rel] = href

        def first(*keys: str) -> str | None:
            for key in keys:
                value = values.get(key.lower())
                if value:
                    return value
            return None

        title = json_ld.get("title") or first(
            "dc:title",
            "dc.title",
            "dcterm:title",
            "dcterm.title",
            "og:title",
            "twitter:title",
            "title",
        )
        byline = json_ld.get("byline") or first(
            "dc:creator",
            "dc.creator",
            "dcterm:creator",
            "dcterm.creator",
            "author",
            "article:author",
        )
        excerpt = json_ld.get("excerpt") or first(
            "dc:description",
            "dc.description",
            "dcterm:description",
            "dcterm.description",
            "description",
            "sailthru.description",
            "og:description",
            "twitter:description",
        )
        image = json_ld.get("image") or first(
            "og:image",
            "twitter:image",
            "twitter:image:src",
        )
        canonical = links.get("canonical")
        metadata = {
            "title": self._clean_title(title) if title else None,
            "byline": self._clean_byline(byline) if byline else None,
            "excerpt": self._normalize_spaces(excerpt) if excerpt else None,
            "siteName": json_ld.get("siteName") or first("og:site_name", "application-name"),
            "image": urljoin(self._base_uri, image) if image else None,
            "canonical": urljoin(self._base_uri, canonical) if canonical else None,
            "publishedTime": (
                json_ld.get("publishedTime")
                or first("article:published_time", "date", "datepublished", "pubdate", "sailthru.date")
            ),
            "modifiedTime": (
                json_ld.get("modifiedTime")
                or first("article:modified_time", "datemodified")
            ),
        }
        for key in ("title", "byline", "excerpt", "siteName", "publishedTime", "modifiedTime"):
            metadata[key] = self._unescape_html_entities(metadata.get(key))
        return metadata

    def _flag_is_active(self, flag: int) -> bool:
        return bool(self._flags & flag)

    def _remove_flag(self, flag: int) -> None:
        self._flags &= ~flag

    def parse(self) -> dict[str, Any] | None:
        """Return article metadata/content, or ``None`` when no article is found."""
        if self._max_elems_to_parse:
            count = len(self._doc.getElementsByTagName("*"))
            if count > self._max_elems_to_parse:
                raise ValueError(f"Aborting parsing document; {count} elements found")

        self._unwrap_noscript_images(self._doc)
        json_ld = self._get_json_ld()
        self._remove_scripts(self._doc)
        self._prep_document()

        metadata = self._get_article_metadata(json_ld)
        self._metadata = metadata
        self._article_title = metadata.get("title") or self._get_article_title()
        self._article_image = metadata.get("image")
        self._article_uri = metadata.get("canonical") or self._article_uri

        article: Element | None = None
        body_nodes = list(self._doc.getElementsByTagName("body"))
        page = body_nodes[0] if body_nodes else self._doc
        page_cache_html = str(getattr(page, "innerHTML", ""))
        while True:
            article = self._grab_article(page)
            if article is not None:
                self._prep_article(article)
                text = self._get_inner_text(article, False)
                if len(text) >= self._char_threshold:
                    self._wrap_readability_page(article)
                    break
                self._attempts.append({"articleContent": article, "textLength": len(text)})
                if hasattr(page, "innerHTML"):
                    page.innerHTML = page_cache_html
            if self._flag_is_active(self.FLAG_STRIP_UNLIKELYS):
                self._remove_flag(self.FLAG_STRIP_UNLIKELYS)
            elif self._flag_is_active(self.FLAG_WEIGHT_CLASSES):
                self._remove_flag(self.FLAG_WEIGHT_CLASSES)
            elif self._flag_is_active(self.FLAG_CLEAN_CONDITIONALLY):
                self._remove_flag(self.FLAG_CLEAN_CONDITIONALLY)
            else:
                if self._attempts:
                    article = max(self._attempts, key=lambda item: item["textLength"])["articleContent"]
                break

        if article is None:
            return None
        self._post_process_content(article)
        text_content = self._get_inner_text(article, False)
        if not text_content:
            return None
        if not metadata.get("excerpt"):
            paragraphs = article.getElementsByTagName("p")
            if paragraphs:
                metadata["excerpt"] = self._get_inner_text(paragraphs[0])
        byline = metadata.get("byline") or self._article_byline
        site_name = metadata.get("siteName") or self._article_site_name
        html_nodes = list(self._doc.getElementsByTagName("html"))
        language = self._attr(html_nodes[0], "lang") if html_nodes else self._attr(self._doc, "lang")
        self._article_dir = self._article_dir or self._attr(article, "dir") or (
            self._attr(html_nodes[0], "dir") if html_nodes else self._attr(self._doc, "dir")
        )
        result = {
            "title": self._article_title or "",
            "byline": byline,
            "uri": self._article_uri,
            "dir": self._article_dir,
            "lang": language or None,
            "content": self._serializer(article),
            "textContent": text_content,
            "length": len(text_content),
            "excerpt": metadata.get("excerpt"),
            "siteName": site_name,
            "image": self._article_image,
            "publishedTime": metadata.get("publishedTime"),
            "modifiedTime": metadata.get("modifiedTime"),
        }
        return result


__all__ = ["Readability"]
