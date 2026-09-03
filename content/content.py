from itertools import count
import html as html_entities
import json
from http.cookiejar import Cookie
from pathlib import Path
import re
import tempfile

import requests
from domonic import domonic
from domonic.events import Event
from domonic.html import (
    article,
    button,
    code,
    div,
    form,
    h1,
    h2,
    h3,
    img,
    input,
    li,
    main,
    p,
    pre,
    script,
    section,
    span,
    style,
    ul,
)
from domonic.webapi.clipboard import Clipboard
from domonic.webapi.history import History
from domonic.webapi.url import URL, URLSearchParams
from domonic.webapi.webstorage import Storage

from domonic_libs import App, on

from domonic_libs.readability import Readability


HOME = "https://en.wikipedia.org/wiki/Special:Random"
CONTENT_SELECTORS = ("h1", "h2", "h3", "p", "blockquote", "pre")
MATH_TEX_ENCODING = "application/x-tex"
DATA_MW_RE = re.compile(r"""\sdata-mw=(?:"[^"]*"|'[^']*')""")
# tex-mml-chtml carries both the TeX and MathML input jaxes, so MathJax can
# typeset the inline "\\(...\\)" TeX and, when "Unified math" is on, the display
# MathML too. A "math-block" carrying "mathjax-ignore" (added by content_node in
# native mode) is left for the browser's own MathML renderer instead.
MATHJAX_SRC = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"
MATHJAX_SETUP = """
window.MathJax = {
    tex: {
        inlineMath: [["\\\\(", "\\\\)"]],
        displayMath: [["\\\\[", "\\\\]"]]
    },
    options: {
        ignoreHtmlClass: "mathjax-ignore",
        skipHtmlTags: ["script", "noscript", "style", "textarea", "pre", "code"]
    }
};
""".strip()
MATHJAX_REFRESH = """
(function () {
    if (window.__contentMathHooked) { return; }
    window.__contentMathHooked = true;

    var scheduled = false;

    function typeset() {
        scheduled = false;
        if (!window.MathJax || !window.MathJax.typesetPromise) { return; }
        observer.disconnect();
        if (window.MathJax.typesetClear) { window.MathJax.typesetClear(); }
        window.MathJax.typesetPromise()
            .catch(function (error) { console.error("MathJax", error); })
            .then(function () {
                observer.observe(document.body, { childList: true, subtree: true });
            });
    }

    function schedule() {
        if (scheduled) { return; }
        scheduled = true;
        window.requestAnimationFrame(typeset);
    }

    var observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true });
    schedule();
})();
""".strip()
IMAGE_ATTRIBUTES = ("src", "data-src", "data-lazy-src", "data-original")
FAVICON_RELS = ("icon", "shortcut icon", "apple-touch-icon", "mask-icon")
USER_AGENT = "Mozilla/5.0 domonic-libs-content/0.1 reader-harness"
TRACKING_PARAMS = {
    "dclid",
    "fbclid",
    "gclid",
    "gbraid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "oly_anon_id",
    "oly_enc_id",
    "vero_id",
    "wbraid",
    "yclid",
}

app = App("Content", width=1120, height=760, debug=False, text_select=True)
tab_ids = count(1)
session = requests.Session()
clipboard = Clipboard()
state = {
    "active": "",
    "tabs": [],
    "settings": {
        "ui_font_size": 12,
        "reader_font_size": 16,
        "show_settings": False,
        "private_load_images": False,
        "unify_math": False,
    },
    "closed_tabs": [],
}
restoring_state = False


def make_browser_storage():
    try:
        return Storage(str(app.data_path("webstorage.json")))
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "domonic-libs-content-webstorage.json"
        return Storage(str(fallback))


browser_storage = make_browser_storage()


class NoCookieJar(requests.cookies.RequestsCookieJar):
    def set_cookie(self, cookie: Cookie, *args, **kwargs):
        return None


def private_session():
    client = requests.Session()
    client.cookies = NoCookieJar()
    return client


def new_tab_data(*, incognito=False):
    tab_id = f"tab-{next(tab_ids)}"
    return {
        "id": tab_id,
        "incognito": incognito,
        "draft_url": HOME,
        "current_url": "",
        "title": "Incognito" if incognito else "New Tab",
        "favicon": "",
        "metadata": {},
        "items": [],
        "images": [],
        "links": [],
        "history": History(),
        "status": (
            "Incognito tab. Local history is discarded when this tab closes."
            if incognito
            else "Paste a URL and press Go."
        ),
    }


def history_from_urls(urls, index):
    history = History()
    for url in urls or []:
        if url:
            history.pushState({"url": url}, "", url)
    if history.length:
        history.index = clamp(int(index), 0, history.length - 1)
    return history


def tab_snapshot(tab):
    return {
        "draft_url": tab["draft_url"],
        "current_url": tab["current_url"],
        "title": tab["title"],
        "favicon": tab["favicon"],
        "metadata": tab["metadata"],
        "items": tab["items"],
        "images": tab["images"],
        "links": tab["links"],
        "history": list(tab["history"].states),
        "history_index": tab["history"].index,
        "status": tab["status"],
    }


def save_browser_state():
    if restoring_state:
        return
    public_tabs = [tab for tab in state["tabs"] if not tab["incognito"]]
    active_index = next(
        (index for index, tab in enumerate(public_tabs) if tab["id"] == state["active"]),
        0,
    )
    data = {
        "active_index": active_index,
        "settings": state["settings"],
        "tabs": [tab_snapshot(tab) for tab in public_tabs],
        "closed_tabs": state["closed_tabs"][:10],
    }
    try:
        browser_storage.setItem("content.state", json.dumps(data))
    except OSError:
        browser_storage.has_file = False
        browser_storage.setItem("content.state", json.dumps(data))


def restore_browser_state():
    global restoring_state
    restoring_state = True
    try:
        raw = browser_storage.getItem("content.state")
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}

    saved_settings = data.get("settings") if isinstance(data, dict) else None
    if isinstance(saved_settings, dict):
        state["settings"]["ui_font_size"] = clamp(int(saved_settings.get("ui_font_size", 12)), 10, 18)
        state["settings"]["reader_font_size"] = clamp(int(saved_settings.get("reader_font_size", 16)), 13, 24)
        state["settings"]["show_settings"] = bool(saved_settings.get("show_settings", False))
        state["settings"]["private_load_images"] = bool(saved_settings.get("private_load_images", False))
        state["settings"]["unify_math"] = bool(saved_settings.get("unify_math", False))
    state["closed_tabs"] = data.get("closed_tabs", [])[:10] if isinstance(data, dict) else []

    saved_tabs = data.get("tabs", []) if isinstance(data, dict) else []
    for saved in saved_tabs:
        if not isinstance(saved, dict):
            continue
        tab = new_tab_data()
        tab.update(
            {
                "draft_url": saved.get("draft_url") or saved.get("current_url") or HOME,
                "current_url": saved.get("current_url", ""),
                "title": saved.get("title") or "New Tab",
                "favicon": saved.get("favicon", ""),
                "metadata": saved.get("metadata") if isinstance(saved.get("metadata"), dict) else {},
                "items": saved.get("items") if isinstance(saved.get("items"), list) else [],
                "images": saved.get("images") if isinstance(saved.get("images"), list) else [],
                "links": saved.get("links") if isinstance(saved.get("links"), list) else [],
                "history": history_from_urls(saved.get("history", []), saved.get("history_index", -1)),
                "status": saved.get("status") or "Restored tab.",
            }
        )
        state["tabs"].append(tab)

    if state["tabs"]:
        active_index = data.get("active_index", 0) if isinstance(data, dict) else 0
        state["active"] = state["tabs"][clamp(int(active_index), 0, len(state["tabs"]) - 1)]["id"]
    else:
        create_tab()
    restoring_state = False


def current_tab():
    if not state["tabs"]:
        create_tab()

    for tab in state["tabs"]:
        if tab["id"] == state["active"]:
            return tab

    state["active"] = state["tabs"][0]["id"]
    return state["tabs"][0]


def create_tab(event=None, *, incognito=False):
    tab = new_tab_data(incognito=incognito)
    state["tabs"].append(tab)
    state["active"] = tab["id"]
    save_browser_state()


def create_incognito_tab(event=None):
    create_tab(event, incognito=True)


def switch_tab(tab_id):
    def handler(event):
        if any(tab["id"] == tab_id for tab in state["tabs"]):
            state["active"] = tab_id
            save_browser_state()

    return handler


def close_tab(tab_id):
    def handler(event):
        closing = next((tab for tab in state["tabs"] if tab["id"] == tab_id), None)
        remember_closed_tab(closing)

        if len(state["tabs"]) == 1:
            state["tabs"] = []
            create_tab()
            save_browser_state()
            return

        index = next(
            (i for i, tab in enumerate(state["tabs"]) if tab["id"] == tab_id),
            -1,
        )

        if index < 0:
            return

        del state["tabs"][index]

        if state["active"] == tab_id:
            state["active"] = state["tabs"][max(0, index - 1)]["id"]
        save_browser_state()

    return handler


def remember_closed_tab(tab):
    if not tab or tab.get("incognito") or not tab.get("current_url"):
        return

    state["closed_tabs"].insert(
        0,
        {
            "title": tab.get("title") or tab.get("current_url"),
            "url": tab.get("current_url"),
            "favicon": tab.get("favicon", ""),
        },
    )
    state["closed_tabs"] = state["closed_tabs"][:10]


def normalize_url(value):
    value = (value or "").strip()

    if not value:
        return ""

    parsed = URL(value)
    if parsed.protocol in {"http", "https"} and parsed.hostname:
        return parsed.href

    # Looks like a hostname/domain
    if (
        "." in value
        and " " not in value
        and "\t" not in value
        and "\n" not in value
    ):
        return "https://" + value

    # Otherwise treat it as a Google search
    return "https://www.mojeek.com/search?" + URLSearchParams({"q": value}).toString()


def strip_tracking_params(url):
    parsed = URL(url)
    search = parsed.search or ""

    if not search.startswith("?"):
        return parsed.href

    params = URLSearchParams(search[1:])
    changed = False

    for key in list(params.keys()):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_PARAMS:
            params.delete(key)
            changed = True

    if not changed:
        return parsed.href

    query = params.toString()
    parsed.search = f"?{query}" if query else ""
    return parsed.href


def text_of(node):
    text = getattr(node, "textContent", "") or ""
    return " ".join(text.split())


def tag_of(node):
    return (getattr(node, "tagName", "") or "").lower()


def attr_of(node, name):
    if hasattr(node, "getAttribute"):
        value = node.getAttribute(name)

        if value:
            return value

    return getattr(node, name.replace("-", "_"), "") or ""


def absolute_url(base_url, value):
    value = (value or "").strip()

    if value.startswith("//"):
        parsed = URL(base_url)
        return f"{parsed.protocol or 'https'}:{value}"

    try:
        return URL(value, base_url).href
    except Exception:
        return value


def current_history_url(tab):
    history = tab["history"]

    if history.index < 0 or history.index >= len(history.states):
        return ""

    return history.states[history.index]


def can_go_back(tab):
    return tab["history"].index > 0


def can_go_forward(tab):
    history = tab["history"]
    return 0 <= history.index < len(history.states) - 1


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def event_value(event, fallback):
    target = getattr(event, "target", None)
    value = getattr(target, "value", fallback)

    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def event_checked(event, fallback=False):
    target = getattr(event, "target", None)

    if hasattr(target, "checked"):
        return bool(getattr(target, "checked"))

    value = getattr(target, "value", fallback)
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}

    return bool(value)


def toggle_settings(event=None):
    state["settings"]["show_settings"] = not state["settings"].get("show_settings", False)
    save_browser_state()


def set_ui_font_size(event):
    state["settings"]["ui_font_size"] = clamp(event_value(event, 12), 10, 18)
    save_browser_state()


def set_reader_font_size(event):
    state["settings"]["reader_font_size"] = clamp(event_value(event, 16), 13, 24)
    save_browser_state()


def reset_font_sizes(event):
    state["settings"]["ui_font_size"] = 12
    state["settings"]["reader_font_size"] = 16
    save_browser_state()


def set_private_load_images(event):
    state["settings"]["private_load_images"] = event_checked(event)
    save_browser_state()


def set_unify_math(event):
    state["settings"]["unify_math"] = event_checked(event)
    save_browser_state()


def collect_items(document):
    items = []
    seen = set()
    allowed = set(CONTENT_SELECTORS)

    for node in document.getElementsByTagName("*"):
        tag = tag_of(node)

        if "math-block" in _node_class(node):
            math_nodes = node.getElementsByTagName("math")
            if not math_nodes:
                continue
            mathml = str(math_nodes[0])
            tex = attr_of(node, "data-tex")
            key = tex or mathml
            if key in seen:
                continue
            seen.add(key)
            items.append({"tag": "math", "mathml": mathml, "tex": tex})
            if len(items) >= 80:
                break
            continue

        if tag not in allowed:
            continue

        text = text_of(node)

        if len(text) < 2 or text in seen:
            continue

        seen.add(text)
        items.append({"tag": tag, "text": text})

        if len(items) >= 80:
            break

    return items


def collect_images(document, url):
    images = []
    image_seen = set()
    for node in document.querySelectorAll("img"):
        source = ""

        for attr in IMAGE_ATTRIBUTES:
            source = attr_of(node, attr)

            if source:
                break

        if not source:
            continue

        image_url = absolute_url(url, source)

        if image_url in image_seen:
            continue

        image_seen.add(image_url)
        images.append(
            {
                "src": image_url,
                "alt": attr_of(node, "alt") or "Page image",
            }
        )

        if len(images) >= 12:
            break

    return images


def collect_favicon(document, url):
    for node in document.querySelectorAll("link"):
        rel = " ".join(attr_of(node, "rel").lower().split())
        href = attr_of(node, "href")

        if href and any(item in rel for item in FAVICON_RELS):
            return absolute_url(url, href)

    return ""


def add_image(images, src, alt, url):
    image_url = absolute_url(url, src)
    if not image_url or any(image["src"] == image_url for image in images):
        return

    images.insert(0, {"src": image_url, "alt": alt or "Page image"})


def collect_links(document, url):
    links = []
    for node in document.querySelectorAll("a"):
        text = text_of(node)
        href = attr_of(node, "href")

        if not text or not href:
            continue

        links.append({"text": text[:80], "href": absolute_url(url, href)})

        if len(links) >= 20:
            break

    return links


def strip_parsoid_noise(html_text):
    """Drop Parsoid ``data-mw`` attributes before the HTML is parsed.

    Wikipedia now serves Parsoid markup where templated blocks carry a large
    ``data-mw`` JSON attribute whose value contains double quotes. domonic
    parses it correctly, but when Readability re-serialises the article the
    attribute comes back out as ``data-mw="{"parts":..."`` with the inner
    quotes unescaped, so the re-parse terminates the attribute early and spills
    the rest of the JSON into the visible text. Nothing in the reader needs the
    attribute, so remove it up front. See ``docs/domonic-wrinkles.md``.
    """
    return DATA_MW_RE.sub("", html_text)


def _node_class(node):
    if hasattr(node, "getAttribute"):
        return node.getAttribute("class") or ""
    return ""


def _math_tex(math_node):
    for annotation in math_node.getElementsByTagName("annotation"):
        if (annotation.getAttribute("encoding") or "") == MATH_TEX_ENCODING:
            return html_entities.unescape(annotation.textContent or "").strip()
    return ""


def rewrite_math(document):
    """Rewrite Wikipedia math islands for the webview.

    Each formula ships as MathML hidden behind ``display: none``, an
    ``application/x-tex`` annotation, and an ``aria-hidden`` raster fallback --
    and Readability drops every one of those as invisible. So before extraction:

    * **Display formulas** keep their MathML, lifted into a visible
      ``div.math-block`` (annotation stripped). WebKit and current Chromium
      render MathML natively, so the reader shows real typeset math with no
      script. This also exercises domonic's MathML round-tripping, which is a
      stated purpose of this repo.
    * **Inline formulas** become their TeX wrapped in MathJax ``\\(...\\)``
      delimiters. Inline ``<math>`` would be flattened to unspaced glyphs by the
      text-only reader, whereas delimited TeX rides along in the paragraph text
      and MathJax lays it out. MathJax is also the fallback for any webview
      whose MathML support is weak.

    The raw TeX is kept on ``data-tex`` so copy and "save as Markdown" work.
    """
    for math_node in list(document.getElementsByTagName("math")):
        tex = _math_tex(math_node)

        container = math_node
        ancestors = []
        paragraph = None
        node = math_node
        for _ in range(5):
            node = getattr(node, "parentNode", None)
            if node is None:
                break
            ancestors.append(node)
            if "mwe-math-element" in _node_class(node):
                container = node
            if paragraph is None and (getattr(node, "tagName", "") or "").lower() == "p":
                paragraph = node

        parent = container.parentNode
        if parent is None:
            continue

        block = (
            "mwe-math-element-block" in _node_class(container)
            or (math_node.getAttribute("display") or "").lower() == "block"
            or any("equation-box" in _node_class(item) for item in ancestors)
        )

        if block:
            for annotation in list(math_node.getElementsByTagName("annotation")):
                annotation.parentNode.removeChild(annotation)

            wrapper = document.createElement("div")
            wrapper.setAttribute("class", "math-block")
            if tex:
                wrapper.setAttribute("data-tex", tex)
            wrapper.appendChild(math_node)

            target = (
                paragraph
                if paragraph is not None and paragraph.parentNode is not None
                else container
            )
            target.parentNode.replaceChild(wrapper, target)
        elif tex:
            parent.replaceChild(
                document.createTextNode(f" \\({tex}\\) "), container
            )


def parse_page(html_text):
    document = domonic.parseString(html_text)
    rewrite_math(document)
    return document


def extract_with_readability(document, url, *, favicon=""):
    document.URL = url
    result = Readability(
        document, char_threshold=120, classes_to_preserve=["math-block"]
    ).parse()

    if not result:
        return None

    article_document = domonic.parseString(result["content"])
    title_text = result["title"] or url
    items = collect_items(article_document)
    images = collect_images(article_document, url)
    if result.get("image"):
        add_image(images, result["image"], result.get("title"), url)
    links = collect_links(article_document, url)

    if not items:
        paragraphs = [line.strip() for line in result["textContent"].splitlines() if line.strip()]
        items = [{"tag": "p", "text": line} for line in paragraphs[:80]]

    metadata = {
        key: result.get(key)
        for key in ("byline", "excerpt", "siteName", "publishedTime", "modifiedTime", "lang", "dir", "image", "uri")
        if result.get(key)
    }
    if favicon:
        metadata["favicon"] = favicon

    return title_text, items, images, links, metadata


def extract_content(html_text, url):
    html_text = strip_parsoid_noise(html_text)
    document = parse_page(html_text)
    favicon = collect_favicon(document, url)
    readable = extract_with_readability(document, url, favicon=favicon)

    if readable:
        return readable

    document = parse_page(html_text)
    title_nodes = document.querySelectorAll("title")
    title_text = text_of(title_nodes[0]) if title_nodes else url
    items = collect_items(document)
    images = collect_images(document, url)
    links = collect_links(document, url)
    metadata = {"favicon": favicon} if favicon else {}

    return title_text, items, images, links, metadata


def fetch_url(url, *, incognito=False):
    headers = {"User-Agent": USER_AGENT}
    client = session

    if incognito:
        client = private_session()
        headers.update(
            {
                "Cache-Control": "no-store",
                "Cookie": "",
                "DNT": "1",
                "Pragma": "no-cache",
                "Sec-GPC": "1",
            }
        )

    response = client.get(url, timeout=12, headers=headers)
    response.raise_for_status()
    return response.text, response.url


def load_url(url, *, push=True, tab=None):
    tab = tab or current_tab()
    url = normalize_url(url)
    if tab["incognito"]:
        url = strip_tracking_params(url)

    if not url:
        tab["status"] = "Enter a valid http or https URL."
        return

    tab["status"] = f"Loading {url}..."

    try:
        html_text, final_url = fetch_url(url, incognito=tab["incognito"])
        title_text, items, images, links, metadata = extract_content(html_text, final_url)
    except Exception as error:
        tab["status"] = f"Could not load {url}: {type(error).__name__}: {error}"
        return

    if push:
        tab["history"].pushState({"url": final_url}, title_text, final_url)

    tab["current_url"] = final_url
    tab["draft_url"] = final_url
    tab["title"] = title_text
    tab["metadata"] = metadata
    tab["favicon"] = "" if tab["incognito"] else metadata.get("favicon", "")
    tab["items"] = items
    tab["images"] = images
    tab["links"] = links
    tab["status"] = (
        f"{'Incognito loaded' if tab['incognito'] else 'Loaded'} "
        f"{len(items)} content blocks and {len(images)} images from {final_url}"
    )
    if tab["incognito"] and images and not state["settings"].get("private_load_images", False):
        tab["status"] += " (remote images listed, not auto-loaded)"
    save_browser_state()


def go(event):
    tab = current_tab()
    form_data = getattr(getattr(event, "target", None), "formData", None)
    url = getattr(form_data, "url", tab["draft_url"])
    load_url(url, tab=tab)


def go_back(event):
    tab = current_tab()

    if not can_go_back(tab):
        tab["status"] = "No previous page."
        return

    tab["history"].back()
    load_url(current_history_url(tab), push=False, tab=tab)


def go_forward(event):
    tab = current_tab()

    if not can_go_forward(tab):
        tab["status"] = "No forward page."
        return

    tab["history"].forward()
    load_url(current_history_url(tab), push=False, tab=tab)


def reload_page(event):
    tab = current_tab()

    if not tab["current_url"]:
        tab["status"] = "Nothing to reload."
        return

    load_url(tab["current_url"], push=False, tab=tab)


def random_page(event):
    load_url(HOME, tab=current_tab())


def recent_history_entries(limit=12):
    entries = []
    seen = set()
    for tab in reversed(state["tabs"]):
        if tab.get("incognito"):
            continue
        states = list(getattr(tab["history"], "states", []))
        for url in reversed(states):
            if not url or url in seen:
                continue
            seen.add(url)
            entries.append(
                {
                    "title": tab.get("title") if url == tab.get("current_url") else url,
                    "url": url,
                    "favicon": tab.get("favicon", "") if url == tab.get("current_url") else "",
                }
            )
            if len(entries) >= limit:
                return entries
    return entries


def open_history_url(url):
    def handler(event=None):
        load_url(url, tab=current_tab())

    return handler


def reopen_closed_tab(url, title="Restored tab"):
    def handler(event=None):
        create_tab()
        tab = current_tab()
        tab["title"] = title or "Restored tab"
        load_url(url, tab=tab)

    return handler


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "content"


def metadata_lines(metadata):
    lines = []
    labels = {
        "byline": "By",
        "siteName": "Site",
        "publishedTime": "Published",
        "modifiedTime": "Modified",
        "lang": "Language",
        "uri": "Reader URI",
    }
    for key, label in labels.items():
        value = metadata.get(key)
        if value:
            lines.append(f"{label}: {value}")
    return lines


def markdown_link(label, href):
    label = (label or href).replace("[", "\\[").replace("]", "\\]")
    href = (href or "").replace(")", "%29")
    return f"[{label}]({href})"


def page_markdown(tab):
    lines = [
        f"# {tab['title']}",
        "",
        f"URL: {tab['current_url'] or tab['draft_url']}",
    ]
    meta = metadata_lines(tab.get("metadata", {}))

    if meta:
        lines.extend(meta)

    excerpt = tab.get("metadata", {}).get("excerpt")
    if excerpt:
        lines.extend(["", excerpt])

    lines.append("")

    if tab["images"]:
        lines.append("## Images")

        for image in tab["images"]:
            lines.append(f"- ![{image['alt']}]({image['src']})")

        lines.append("")

    if tab["items"]:
        lines.append("## Content")

        for item in tab["items"]:
            if item["tag"] == "math":
                tex = item.get("tex", "").strip()
                if tex:
                    lines.extend(["", "$$", tex, "$$", ""])
                continue

            text = item["text"]

            if item["tag"] == "h1":
                lines.extend(["", f"# {text}"])
            elif item["tag"] == "h2":
                lines.extend(["", f"## {text}"])
            elif item["tag"] == "h3":
                lines.extend(["", f"### {text}"])
            elif item["tag"] == "blockquote":
                lines.append("> " + text.replace("\n", "\n> "))
            elif item["tag"] == "pre":
                lines.extend(["```", text, "```"])
            else:
                lines.append(text)

        lines.append("")

    if tab["links"]:
        lines.append("## Links")

        for link in tab["links"]:
            lines.append(f"- {markdown_link(link['text'], link['href'])}")

    return "\n".join(lines).strip() + "\n"


def page_text(tab):
    return page_markdown(tab)


def save_page(event):
    tab = current_tab()

    if not tab["items"] and not tab["images"]:
        tab["status"] = "Nothing loaded to save."
        return

    path = app.save_file(
        filename=f"{slugify(tab['title'])}.md",
        file_types=(
            "Markdown files (*.md)",
            "Text files (*.txt)",
            "All files (*.*)",
        ),
    )
    path = path[0] if isinstance(path, (list, tuple)) and path else path

    if not path:
        tab["status"] = "Save canceled."
        return

    path = Path(path)

    if path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        path = path.with_suffix(".md")

    path.write_text(page_markdown(tab), encoding="utf-8")
    tab["status"] = f"Saved {path.name}"
    save_browser_state()


def copy_text(label, text):
    tab = current_tab()
    if not text:
        tab["status"] = f"Nothing to copy for {label}."
        return
    try:
        clipboard.writeText(text)
        tab["status"] = f"Copied {label}."
    except Exception as error:
        tab["status"] = f"Could not copy {label}: {type(error).__name__}: {error}"


def copy_url(event=None):
    tab = current_tab()
    copy_text("URL", tab["current_url"] or tab["draft_url"])


def copy_title_and_url(event=None):
    tab = current_tab()
    url = tab["current_url"] or tab["draft_url"]
    copy_text("title and URL", f"{tab['title']}\n{url}" if url else "")


def copy_markdown(event=None):
    tab = current_tab()
    if not tab["items"] and not tab["images"]:
        tab["status"] = "Nothing loaded to copy."
        return
    copy_text("Markdown", page_markdown(tab))


def open_link(href):
    def handler(event):
        load_url(href, tab=current_tab())

    return handler


def nav_button(label, callback, *, disabled=False, title=""):
    attrs = {"_type": "button"}

    if title:
        attrs["_title"] = title
        attrs["_aria_label"] = title

    if disabled:
        attrs["_disabled"] = "disabled"

    return on(button(label, **attrs), Event.CLICK, callback)


def url_input(tab):
    return input(
        _type="text",
        _name="url",
        _value=tab["draft_url"],
        _placeholder=HOME,
        _autocomplete="off",
        _autocorrect="off",
        _spellcheck="false",
    )


def range_control(name, value, minimum, maximum, callback, title):
    return span(
        span(name, _class="settings-label"),
        on(
            input(
                _type="range",
                _min=str(minimum),
                _max=str(maximum),
                _value=str(value),
                _title=title,
                _aria_label=title,
            ),
            Event.CHANGE,
            callback,
        ),
        _class="settings-control",
    )


def checkbox_control(name, checked, callback, title):
    attrs = {
        "_type": "checkbox",
        "_title": title,
        "_aria_label": title,
    }

    if checked:
        attrs["_checked"] = "checked"

    return span(
        on(input(**attrs), Event.CHANGE, callback),
        span(name, _class="settings-label"),
        _class="settings-control checkbox-control",
    )


def content_node(item):
    tag = item["tag"]

    if tag == "math":
        css_class = "math-block"
        if not state["settings"].get("unify_math", False):
            css_class += " mathjax-ignore"
        node = div(_class=css_class)
        node.innerHTML = item["mathml"]
        return node

    text = item["text"]

    if tag == "h1":
        return h1(text)
    if tag == "h2":
        return h2(text)
    if tag == "h3":
        return h3(text)
    if tag == "pre":
        return pre(code(text))
    if tag == "blockquote":
        return section(p(text), _class="quote")

    return p(text)


def image_node(image, *, private=False):
    if private and not state["settings"].get("private_load_images", False):
        return div(
            span(image["alt"], _class="private-media-title"),
            code(image["src"]),
            _class="private-media",
        )

    return img(_src=image["src"], _alt=image["alt"], _loading="lazy")


def link_node(link):
    return li(
        on(
            button(
                link["text"],
                _type="button",
                _class="link-button",
                _title=link["href"],
            ),
            Event.CLICK,
            open_link(link["href"]),
        )
    )


def metadata_node(tab):
    lines = metadata_lines(tab.get("metadata", {}))
    excerpt = tab.get("metadata", {}).get("excerpt")

    if not lines and not excerpt:
        return ""

    return div(
        *(p(line) for line in lines),
        (p(excerpt, _class="excerpt") if excerpt else ""),
        _class="metadata",
    )


def favicon_node(tab):
    if tab.get("incognito"):
        return span("", _class="favicon empty-favicon")

    if not tab.get("favicon"):
        return span("", _class="favicon empty-favicon")

    return img(_src=tab["favicon"], _alt="", _class="favicon")


def tab_title(tab):
    prefix = "Private: " if tab["incognito"] else ""
    title = tab["title"] or "New Tab"
    return prefix + (title[:28] + "..." if len(title) > 31 else title)


def tab_button(tab):
    classes = ["tab"]

    if tab["id"] == state["active"]:
        classes.append("active")

    if tab["incognito"]:
        classes.append("incognito")

    return div(
        on(
            button(
                favicon_node(tab),
                span(tab_title(tab), _class="tab-label"),
                _type="button",
                _class="tab-title",
                _title=tab["title"],
            ),
            Event.CLICK,
            switch_tab(tab["id"]),
        ),
        on(
            button("x", _type="button", _class="tab-close"),
            Event.CLICK,
            close_tab(tab["id"]),
        ),
        _class=" ".join(classes),
    )


app.menu(
    "File",
    app.menu_item("New Tab", create_tab),
    app.menu_item("New Incognito Tab", create_incognito_tab),
    app.menu_separator(),
    app.menu_item("Save Page As Markdown...", save_page),
)
app.menu(
    "Edit",
    app.menu_item("Copy URL", copy_url, refresh=False),
    app.menu_item("Copy Title and URL", copy_title_and_url, refresh=False),
    app.menu_item("Copy Page as Markdown", copy_markdown, refresh=False),
)
app.menu(
    "History",
    app.menu_item("Back", go_back),
    app.menu_item("Forward", go_forward),
    app.menu_item("Reload", reload_page),
    app.menu_separator(),
    app.menu_item("Random Wikipedia Page", random_page),
)

restore_browser_state()


@app.route("/")
def index():
    tab = current_tab()
    history = tab["history"]

    return main(
        style(
            """
            @import url("https://cdn.jsdelivr.net/npm/milligram@1.4.1/dist/milligram.min.css");

            :root {
                --ui-font-size: __UI_FONT_SIZE__px;
                --reader-font-size: __READER_FONT_SIZE__px;
                color-scheme: light;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }

            body {
                margin: 0;
                padding: 0;
                background: #eef2f5;
                color: #1f2328;
                font-size: var(--ui-font-size);
            }

            main.app-shell {
                height: 100vh;
                display: grid;
                grid-template-rows: auto auto auto minmax(0, 1fr) auto;
                overflow: hidden;
            }

            main.app-shell > style {
                display: none;
            }

            .tabs {
                grid-row: 1;
                display: flex;
                gap: 4px;
                padding: 6px 8px 0;
                background: #dde5ee;
                overflow-x: auto;
            }

            .tab {
                display: flex;
                align-items: center;
                min-width: 90px;
                max-width: 180px;
                border: 1px solid #c8d1dc;
                border-bottom: 0;
                border-radius: 5px 5px 0 0;
                background: #eef2f5;
                overflow: hidden;
            }

            .tab.active {
                background: #ffffff;
            }

            .tab.incognito {
                background: #29233a;
                border-color: #29233a;
            }

            .tab.incognito button {
                color: #ffffff;
            }

            .tab-title,
            .tab-close {
                min-height: 24px;
                height: 24px;
                line-height: 22px;
                border: 0;
                border-radius: 0;
                background: transparent;
                font-size: var(--ui-font-size);
            }

            .tab-title {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                min-width: 0;
                flex: 1;
                overflow: hidden;
                text-align: left;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .tab-label {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .favicon {
                width: 14px;
                height: 14px;
                flex: 0 0 14px;
                object-fit: contain;
            }

            .empty-favicon {
                display: inline-block;
            }

            .tab-close {
                width: 24px;
                padding: 0;
            }

            .new-tab {
                min-height: 24px;
                height: 24px;
                line-height: 22px;
                margin-left: 2px;
            }

            .toolbar {
                grid-row: 2;
                position: relative;
                z-index: 3;
                display: grid;
                grid-template-columns: repeat(6, 28px) minmax(220px, 1fr) 34px;
                gap: 5px;
                align-items: center;
                padding: 6px 8px;
                border-bottom: 1px solid #c8d1dc;
                background: #ffffff;
                box-sizing: border-box;
            }

            .settings {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 10px;
                padding: 4px 8px;
                border-bottom: 1px solid #d0d7de;
                background: #f6f8fa;
            }

            .settings-drawer {
                grid-row: 3;
                position: relative;
                z-index: 3;
                border-bottom: 1px solid #d0d7de;
                background: #f6f8fa;
            }

            .settings-drawer .settings {
                border-bottom: 0;
            }

            .settings-control {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                white-space: nowrap;
            }

            .settings-control input {
                width: 90px;
            }

            .checkbox-control input {
                width: auto;
                height: auto;
                min-height: 0;
                margin: 0;
            }

            .settings-label {
                color: #57606a;
                font-size: calc(var(--ui-font-size) - 1px);
            }

            button {
                min-height: 26px;
                height: 26px;
                line-height: 24px;
                border: 1px solid #8c959f;
                border-radius: 4px;
                background: #ffffff;
                color: #24292f;
                cursor: pointer;
                font-size: var(--ui-font-size);
                padding: 0 8px;
                margin: 0;
            }

            button:disabled {
                color: #8c959f;
                cursor: default;
                background: #f6f8fa;
            }

            input {
                width: 100%;
                min-height: 26px;
                height: 26px;
                border: 1px solid #8c959f;
                border-radius: 4px;
                background: #ffffff;
                color: #1f2328;
                box-sizing: border-box;
                font-size: var(--ui-font-size);
                padding: 0 8px;
                margin: 0;
            }

            .reader {
                grid-row: 4;
                position: relative;
                z-index: 1;
                min-width: 0;
                min-height: 0;
                overflow: auto;
                display: grid;
                grid-template-columns: minmax(0, 1fr) 260px;
                gap: 24px;
                padding: 22px;
                box-sizing: border-box;
                font-size: var(--reader-font-size);
            }

            article,
            .links {
                background: #ffffff;
                border: 1px solid #d0d7de;
                border-radius: 8px;
                box-sizing: border-box;
            }

            article {
                max-width: 760px;
                min-width: 0;
                padding: 24px;
            }

            .links {
                align-self: start;
                min-width: 0;
                padding: 16px;
            }

            h1 {
                margin: 0 0 18px;
                font-size: calc(var(--reader-font-size) * 1.7);
                line-height: 1.15;
            }

            h2, h3 {
                margin: 24px 0 10px;
            }

            p {
                line-height: 1.62;
            }

            mjx-container {
                max-width: 100%;
                overflow-x: auto;
                overflow-y: hidden;
            }

            mjx-container[display="true"] {
                margin: 1em 0;
            }

            .math-block {
                margin: 1em 0;
                overflow-x: auto;
                overflow-y: hidden;
                text-align: center;
            }

            .math-block math {
                font-size: 1.15em;
            }

            .metadata {
                margin: -6px 0 22px;
                color: #57606a;
                font-size: calc(var(--reader-font-size) * 0.86);
            }

            .metadata p {
                margin: 4px 0;
                line-height: 1.35;
            }

            .metadata .excerpt {
                margin-top: 10px;
            }

            .gallery {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 12px;
                margin: 0 0 22px;
            }

            .gallery img {
                width: 100%;
                max-height: 180px;
                object-fit: contain;
                border: 1px solid #d0d7de;
                border-radius: 8px;
                background: #f6f8fa;
            }

            .private-media {
                display: grid;
                gap: 6px;
                padding: 10px;
                border: 1px solid #d0d7de;
                border-radius: 8px;
                background: #f6f8fa;
            }

            .private-media-title {
                font-size: calc(var(--reader-font-size) * 0.8);
                color: #57606a;
            }

            .private-media code {
                overflow-wrap: anywhere;
                white-space: normal;
                font-size: calc(var(--reader-font-size) * 0.72);
            }

            .quote {
                border-left: 4px solid #0969da;
                padding-left: 14px;
                color: #57606a;
            }

            ul {
                margin: 0;
                padding-left: 20px;
            }

            li {
                margin: 8px 0;
            }

            .link-button {
                display: inline;
                min-height: 0;
                border: 0;
                background: transparent;
                color: #0969da;
                padding: 0;
                text-align: left;
                text-decoration: underline;
            }

            .empty {
                color: #57606a;
            }

            .status {
                grid-row: 5;
                display: flex;
                justify-content: space-between;
                gap: 12px;
                min-height: 30px;
                padding: 6px 10px;
                border-top: 1px solid #c8d1dc;
                color: #57606a;
                background: #ffffff;
                box-sizing: border-box;
                font-size: 13px;
            }

            @media (max-width: 820px) {
                .toolbar,
                .reader {
                    grid-template-columns: 1fr;
                }
            }
            """.replace(
                "__UI_FONT_SIZE__",
                str(state["settings"]["ui_font_size"]),
            ).replace(
                "__READER_FONT_SIZE__",
                str(state["settings"]["reader_font_size"]),
            )
        ),
        script(MATHJAX_SETUP),
        script(_src=MATHJAX_SRC, _id="MathJax-script", _async="async"),
        script(MATHJAX_REFRESH),
        div(
            *[tab_button(item) for item in state["tabs"]],
            on(
                button("+", _type="button", _class="new-tab", _title="New tab", _aria_label="New tab"),
                Event.CLICK,
                create_tab,
            ),
            on(
                button("Private", _type="button", _class="new-tab", _title="New incognito tab"),
                Event.CLICK,
                create_incognito_tab,
            ),
            _class="tabs",
        ),
        on(
            form(
                nav_button("‹", go_back, disabled=not can_go_back(tab), title="Back"),
                nav_button("›", go_forward, disabled=not can_go_forward(tab), title="Forward"),
                nav_button("↻", reload_page, disabled=not tab["current_url"], title="Reload"),
                nav_button("?", random_page, title="Random Wikipedia page"),
                nav_button(
                    "↓",
                    save_page,
                    disabled=not tab["items"] and not tab["images"],
                    title="Save Markdown",
                ),
                nav_button("⚙", toggle_settings, title="Settings"),
                url_input(tab),
                button("Go", _type="submit", _title="Open URL"),
                _class="toolbar",
            ),
            Event.SUBMIT,
            go,
        ),
        (
            div(
                div(
                    range_control(
                        "UI",
                        state["settings"]["ui_font_size"],
                        10,
                        18,
                        set_ui_font_size,
                        "Toolbar and tab text size",
                    ),
                    range_control(
                        "Reader",
                        state["settings"]["reader_font_size"],
                        13,
                        24,
                        set_reader_font_size,
                        "Article text size",
                    ),
                    checkbox_control(
                        "Load Private Images",
                        state["settings"].get("private_load_images", False),
                        set_private_load_images,
                        "Allow private tabs to load remote images",
                    ),
                    checkbox_control(
                        "Unified Math",
                        state["settings"].get("unify_math", False),
                        set_unify_math,
                        "Render display math with MathJax too, so it matches the "
                        "inline formulas (off = native MathML)",
                    ),
                    on(
                        button("Reset", _type="button", _title="Reset font sizes"),
                        Event.CLICK,
                        reset_font_sizes,
                    ),
                    _class="settings",
                ),
                _class="settings-drawer",
            )
            if state["settings"].get("show_settings", False)
            else ""
        ),
        div(
            article(
                h1(tab["title"]),
                metadata_node(tab),
                (
                    div(
                        *[image_node(image, private=tab["incognito"]) for image in tab["images"]],
                        _class="gallery",
                    )
                    if tab["images"]
                    else ""
                ),
                *(
                    [content_node(item) for item in tab["items"]]
                    if tab["items"]
                    else [p("No page loaded yet.", _class="empty")]
                ),
            ),
            section(
                h2("Links"),
                (
                    ul(*[link_node(link) for link in tab["links"]])
                    if tab["links"]
                    else p("No links yet.", _class="empty")
                ),
                _class="links",
            ),
            _class="reader",
        ),
        div(
            span(tab["status"]),
            span(
                ("Incognito, " if tab["incognito"] else "")
                + f"{history.index + 1 if history.length else 0} / {history.length}"
            ),
            _class="status",
        ),
        _class="app-shell",
    )


if __name__ == "__main__":
    app.run()
