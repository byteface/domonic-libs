from domonic_libs.htmlparser2 import (
    DomHandler,
    DomUtils,
    ElementType,
    Parser,
    QuoteType,
    Tokenizer,
    append,
    appendChild,
    createDocumentStream,
    getElementById,
    getElementsByClassName,
    getElementsByTagName,
    getInnerHTML,
    innerText,
    parseDOM,
    parseDocument,
    parseFeed,
    prepend,
    removeElement,
    textContent,
)
from domonic.html import li


def test_parser_streaming_callbacks_match_htmlparser2_shape():
    events = []
    parser = Parser(
        {
            "onopentagname": lambda name: events.append(("openname", name)),
            "onattribute": lambda name, value, quote: events.append(("attr", name, value, quote)),
            "onopentag": lambda name, attrs, implied: events.append(("open", name, attrs, implied)),
            "ontext": lambda data: events.append(("text", data)),
            "onclosetag": lambda name, implied: events.append(("close", name, implied)),
            "onend": lambda: events.append(("end",)),
        }
    )

    parser.write('<DIV ID="x">Hello &amp; ')
    parser.end("<br>world</DIV>")

    assert events == [
        ("openname", "div"),
        ("attr", "id", "x", '"'),
        ("open", "div", {"id": "x"}, False),
        ("text", "Hello "),
        ("text", "&"),
        ("text", " "),
        ("openname", "br"),
        ("open", "br", {}, False),
        ("close", "br", True),
        ("text", "world"),
        ("close", "div", False),
        ("end",),
    ]


def test_parser_implied_close_rules_for_p_and_li():
    events = []
    Parser(
        {
            "onopentag": lambda name, attrs, implied: events.append(("open", name, implied)),
            "onclosetag": lambda name, implied: events.append(("close", name, implied)),
        }
    ).end("<p>one<p>two<ul><li>a<li>b</ul>")

    assert ("close", "p", True) in events
    assert events.count(("close", "li", True)) == 2
    assert events[-2:] == [("close", "li", True), ("close", "ul", False)]


def test_svg_tag_name_adjustments_and_foreign_context():
    events = []
    Parser(
        {
            "onopentag": lambda name, attrs, implied: events.append(("open", name)),
            "onclosetag": lambda name, implied: events.append(("close", name)),
        }
    ).end("<svg><lineargradient><foreignobject><p>x</p></foreignobject></lineargradient></svg>")

    assert ("open", "linearGradient") in events
    assert ("open", "foreignObject") in events
    assert ("close", "foreignObject") in events


def test_domhandler_builds_domonic_document_and_domutils_query_it():
    doc = parseDocument('<ul id="fruits"><li class="apple">Apple</li><li>Orange</li></ul>')
    ul = getElementById("fruits", doc)
    items = getElementsByTagName("li", doc)

    assert getattr(ul, "tagName", "") == "ul"
    assert len(items) == 2
    assert textContent(doc) == "AppleOrange"
    assert DomUtils.getOuterHTML(items[0]) == '<li class="apple">Apple</li>'


def test_create_document_stream_callback_receives_document():
    seen = []
    parser = createDocumentStream(lambda error, document: seen.append((error, document)))
    parser.write("<section><h1>Title</h1>")
    parser.end("<p>Body</p></section>")

    assert seen[0][0] is None
    assert textContent(seen[0][1]) == "TitleBody"


def test_parser_xml_mode_keeps_case_and_self_closes():
    events = []
    Parser(
        {
            "onopentag": lambda name, attrs, implied: events.append(("open", name, attrs)),
            "onclosetag": lambda name, implied: events.append(("close", name, implied)),
        },
        {"xmlMode": True},
    ).end('<Node MixedCase="yes"/>')

    assert events == [
        ("open", "Node", {"MixedCase": "yes"}),
        ("close", "Node", True),
    ]


def test_comments_cdata_declarations_and_processing_instructions():
    events = []
    Parser(
        {
            "oncomment": lambda data: events.append(("comment", data)),
            "onprocessinginstruction": lambda name, data: events.append(("pi", name, data)),
            "oncdatastart": lambda: events.append(("cdata-start",)),
            "ontext": lambda data: events.append(("text", data)),
            "oncdataend": lambda: events.append(("cdata-end",)),
        },
        {"xmlMode": True},
    ).end("<!doctype html><!-- hi --><![CDATA[x<y]]><?xml version='1.0'?>")

    assert ("pi", "!doctype", "!doctype html") in events
    assert ("comment", " hi ") in events
    assert ("cdata-start",) in events
    assert ("text", "x<y") in events
    assert ("cdata-end",) in events
    assert ("pi", "?xml", "?xml version='1.0'") in events


def test_parse_feed_rss_slice():
    feed = parseFeed(
        """
        <rss><channel>
          <title>Example Feed</title>
          <link>https://example.com</link>
          <description>Things</description>
          <item><title>One</title><link>https://example.com/1</link></item>
        </channel></rss>
        """
    )

    assert feed["type"] == "rss"
    assert feed["title"] == "Example Feed"
    assert feed["items"][0]["title"] == "One"


def test_tokenizer_public_helpers_exist():
    assert Tokenizer({"xmlMode": False}, None).xmlMode is False
    assert QuoteType.NoValue == 0


def test_special_raw_text_tags_do_not_parse_inner_lt_as_markup():
    events = []
    Parser(
        {
            "onopentag": lambda name, attrs, implied: events.append(("open", name)),
            "ontext": lambda data: events.append(("text", data)),
            "onclosetag": lambda name, implied: events.append(("close", name)),
        }
    ).end("<script>if (a < b) run()</script><p>after</p>")

    assert events == [
        ("open", "script"),
        ("text", "if (a < b) run()"),
        ("close", "script"),
        ("open", "p"),
        ("text", "after"),
        ("close", "p"),
    ]


def test_rcdata_and_plaintext_special_tag_paths():
    title_events = []
    Parser({"ontext": lambda data: title_events.append(data)}).end("<title>A &amp; B</title>")

    plain_events = []
    Parser(
        {
            "onopentag": lambda name, attrs, implied: plain_events.append(("open", name)),
            "ontext": lambda data: plain_events.append(("text", data)),
            "onclosetag": lambda name, implied: plain_events.append(("close", name, implied)),
        }
    ).end("<plaintext><b>raw</b></plaintext><p>x</p>")

    assert title_events == ["A ", "&", " B"]
    assert plain_events == [
        ("open", "plaintext"),
        ("text", "<b>raw</b></plaintext><p>x</p>"),
        ("close", "plaintext", True),
    ]


def test_entities_follow_html_text_and_attribute_modes():
    text = []
    attrs = []
    Parser(
        {
            "ontext": lambda data: text.append(data),
            "onattribute": lambda name, value, quote: attrs.append((name, value)),
        }
    ).end('<p title="&copy= &copy; &#x80;">&copy &copy; &#128;</p>')

    assert text == ["©", " ", "©", " ", "€"]
    assert attrs == [("title", "&copy= © €")]


def test_xml_entities_are_strict_and_limited():
    text = []
    Parser({"ontext": lambda data: text.append(data)}, {"xmlMode": True}).end(
        "<root>&amp; &amp &copy; &#169;</root>"
    )

    assert text == ["&", " &amp &copy; ", "©"]


def test_domhandler_receives_decoded_entity_text_and_attributes():
    doc = parseDocument('<p title="Tom &amp; Jerry">Tom &amp; Jerry</p>')
    p = getElementsByTagName("p", doc)[0]

    assert p.getAttribute("title") == "Tom & Jerry"
    assert textContent(doc) == "Tom & Jerry"


def test_domhandler_tracks_indices_types_and_siblings():
    closed = []
    handler = DomHandler(options={"withStartIndices": True, "withEndIndices": True}, elementCallback=closed.append)
    Parser(handler).end("<div><span>one</span><span>two</span></div>")
    div = getElementsByTagName("div", handler.root)[0]
    spans = getElementsByTagName("span", handler.root)

    assert handler.root.type == ElementType.Root
    assert div.type == ElementType.Tag
    assert div.startIndex == 0
    assert div.endIndex == len("<div><span>one</span><span>two</span></div>") - 1
    assert spans[0].next is spans[1]
    assert spans[1].prev is spans[0]
    assert closed[-1] is div


def test_domhandler_constructor_backwards_compat_options_first():
    handler = DomHandler({"withStartIndices": True})
    Parser(handler).end("<p>x</p>")

    assert getElementsByTagName("p", handler.root)[0].startIndex == 0


def test_domutils_compat_query_stringify_and_mutation_helpers():
    nodes = parseDOM('<ul id="nav"><li class="active">One</li><li>Two</li></ul>')
    ul = getElementById("nav", nodes)
    items = getElementsByTagName("li", nodes)
    active = getElementsByClassName("active", nodes)

    assert len(nodes) == 1
    assert active == [items[0]]
    assert getInnerHTML(ul) == '<li class="active">One</li><li>Two</li>'
    assert innerText(ul) == "OneTwo"

    removeElement(items[0])
    assert textContent(ul) == "Two"

    prepend(ul.args[0], li("Zero"))
    appendChild(ul, li("Three"))
    append(ul.args[0], li("One"))

    assert textContent(ul) == "ZeroOneTwoThree"
    assert DomUtils.getSiblings(ul.args[1]) == list(ul.args)


def test_install_domonic_parser_backend_for_parse_string():
    from domonic import domonic
    from domonic_libs.htmlparser2 import install_domonic_parser, uninstall_domonic_parser

    original_default = domonic.get_default_parser()
    try:
        install_domonic_parser()
        page = domonic.parseString("<main><h1>Hi</h1></main>", parser="htmlparser2")

        assert domonic.get_active_parser() == "htmlparser2"
        assert page.querySelector("h1").text == "Hi"

        domonic.set_default_parser("htmlparser2")
        assert domonic.get_default_parser() == "htmlparser2"
    finally:
        uninstall_domonic_parser()
        domonic.set_default_parser(original_default)


def test_install_domonic_parser_can_prefer_auto():
    from domonic import domonic
    from domonic_libs.htmlparser2 import install_domonic_parser, uninstall_domonic_parser

    original_default = domonic.get_default_parser()
    try:
        install_domonic_parser(prefer_auto=True)
        page = domonic.parseString("<article><h1>Auto</h1></article>", parser="auto")

        assert domonic.get_active_parser() == "htmlparser2"
        assert page.querySelector("h1").text == "Auto"
    finally:
        uninstall_domonic_parser()
        domonic.set_default_parser(original_default)
