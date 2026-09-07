from domonic_libs.htmlparser2 import DomUtils, Parser, parseDocument, parseFeed


def show_streaming_callbacks():
    events = []

    Parser(
        {
            "onopentag": lambda name, attrs, implied: events.append(("open", name, attrs, implied)),
            "ontext": lambda text: events.append(("text", text)),
            "onclosetag": lambda name, implied: events.append(("close", name, implied)),
        }
    ).end('<section><h1>Hello</h1><p class="lead">A &amp; B</p><p>Second')

    print("Streaming callbacks")
    for event in events:
        print(" ", event)


def show_domonic_document():
    doc = parseDocument("<ul id='items'><li>One<li>Two<li>Three</ul>")
    items = DomUtils.getElementsByTagName("li", doc)

    print("\nDomHandler -> domonic tree")
    print(" ", doc)
    print(" ", "textContent:", DomUtils.textContent(doc))
    print(" ", "li count:", len(items))


def show_feed_parser():
    feed = parseFeed(
        """
        <rss>
          <channel>
            <title>Example Feed</title>
            <link>https://example.com</link>
            <item><title>One</title><link>https://example.com/1</link></item>
          </channel>
        </rss>
        """
    )

    print("\nFeed parser")
    print(" ", feed)


if __name__ == "__main__":
    show_streaming_callbacks()
    show_domonic_document()
    show_feed_parser()
