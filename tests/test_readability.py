import unittest
import re

from domonic import domonic

import content.content as content_app
from domonic.webapi.webstorage import Storage

from content.content import HOME, extract_content, page_text
from domonic_libs.readability import Readability


ARTICLE = """<!doctype html>
<html lang="en"><head>
<title>A useful article title | Example News</title>
<meta name="author" content="Ada Example">
<meta name="description" content="A short description of the useful article.">
<base href="https://example.com/news/">
</head><body>
<nav class="menu">Home About Subscribe</nav>
<main>
  <article class="article content">
    <h1>A useful article title</h1>
    <p>This is the opening paragraph of the article. It contains enough useful prose to be scored as article content, rather than navigation.</p>
    <p>The second paragraph continues the story with several sentences and considerably more detail. Readers should see this prose in the extracted result. It is deliberately substantial.</p>
    <p>Finally, the article ends with another informative paragraph. <a href="sources">Its source is available here</a> for readers who want to learn more.</p>
  </article>
  <aside class="related">Related stories and advertisements</aside>
</main>
<footer>Copyright Example News</footer>
</body></html>"""


def parse_document(source=ARTICLE):
    return domonic.parseString(source, parser="html.parser")


class TestReadability(unittest.TestCase):
    def test_extracts_article_and_metadata(self):
        document = parse_document()
        document.URL = "https://example.com/news/current-story"
        result = Readability(document, char_threshold=100).parse()

        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "A useful article title")
        self.assertEqual(result["byline"], "Ada Example")
        self.assertEqual(result["uri"], "https://example.com/news/current-story")
        self.assertEqual(result["excerpt"], "A short description of the useful article.")
        self.assertIn("opening paragraph", result["textContent"])
        self.assertIn("second paragraph", result["textContent"])
        self.assertNotIn("Related stories", result["textContent"])
        self.assertNotIn("Copyright", result["textContent"])

    def test_resolves_relative_links(self):
        document = parse_document()
        result = Readability(document, char_threshold=100).parse()
        self.assertIn('href="https://example.com/news/sources"', result["content"])

    def test_resolves_relative_media_and_srcset_against_base(self):
        source = ARTICLE.replace(
            '<p>This is the opening paragraph',
            '<img src="hero.jpg" srcset="small.jpg 480w, /large.jpg 960w" '
            'alt="Hero"><p>This is the opening paragraph',
        )
        document = parse_document(source)
        document.URL = "https://example.com/stories/current"
        result = Readability(document, char_threshold=100).parse()

        self.assertIn('src="https://example.com/news/hero.jpg"', result["content"])
        self.assertIn("https://example.com/news/small.jpg 480w", result["content"])
        self.assertIn("https://example.com/large.jpg 960w", result["content"])

    def test_promotes_lazy_image_attributes(self):
        source = ARTICLE.replace(
            '<p>This is the opening paragraph',
            '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" '
            'data-src="photos/real.jpg" '
            'data-srcset="photos/small.jpg 480w, photos/large.jpg 960w" '
            'alt="Lazy"><p>This is the opening paragraph',
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertIn('src="https://example.com/news/photos/real.jpg"', result["content"])
        self.assertIn("https://example.com/news/photos/small.jpg 480w", result["content"])
        self.assertIn("https://example.com/news/photos/large.jpg 960w", result["content"])

    def test_creates_image_inside_lazy_figure(self):
        source = ARTICLE.replace(
            '<p>This is the opening paragraph',
            '<figure data-src="photos/figure.jpg"></figure><p>This is the opening paragraph',
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertIn('src="https://example.com/news/photos/figure.jpg"', result["content"])
        self.assertIn("<img ", result["content"])

    def test_resolves_relative_base_against_document_url(self):
        source = ARTICLE.replace(
            '<base href="https://example.com/news/">',
            '<base href="/features/">',
        )
        document = parse_document(source)
        document.URL = "https://example.com/news/current-story"
        result = Readability(document, char_threshold=100).parse()

        self.assertIn('href="https://example.com/features/sources"', result["content"])

    def test_resolves_hash_links_against_base_when_base_differs_from_document(self):
        source = ARTICLE.replace(
            '<a href="sources">Its source is available here</a>',
            '<a href="#sources">Its source is available here</a>',
        )
        document = parse_document(source)
        document.URL = "https://example.com/news/current-story"
        result = Readability(document, char_threshold=100).parse()

        self.assertIn('href="https://example.com/news/#sources"', result["content"])

    def test_double_breaks_become_paragraphs(self):
        source = """<!doctype html>
<html><head><title>Break Article</title></head><body>
<div class="article content">
Opening line has enough article words to be counted as useful prose for the reader engine.
<br><br>
Second line also has enough words to remain readable and become another paragraph.
<br><br>
Third line closes the story with useful prose.
</div>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=50).parse()

        self.assertIn("<p>", result["content"])
        self.assertIn("</p>", result["content"])
        self.assertIn("Opening line", result["textContent"])
        self.assertIn("Second line", result["textContent"])

    def test_double_breaks_inside_paragraph_do_not_create_nested_paragraphs(self):
        source = """<!doctype html>
<html><head><title>Nested Break Article</title></head><body>
<article class="content">
<p>Opening line has enough useful article words to remain readable.<br><br>Second line should become a sibling paragraph, not an invalid nested paragraph.</p>
<p>Final paragraph gives this article enough useful prose to pass extraction.</p>
</article>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=80).parse()

        self.assertNotIn("<p><p>", result["content"])
        self.assertIn("Second line", result["textContent"])

    def test_inline_divs_become_paragraphs(self):
        source = """<!doctype html>
<html><head><title>Div Article</title></head><body>
<section class="article content">
<div>Opening div has enough useful article words to be treated as paragraph text.</div>
<div>Second div continues the article with more useful prose and a <span>small inline aside</span>.</div>
<div class="share">Share this article everywhere</div>
</section>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=80).parse()

        self.assertIn("<p>", result["content"])
        self.assertIn("small inline aside", result["textContent"])
        self.assertNotIn("Share this article", result["textContent"])

    def test_loose_text_inside_block_div_is_wrapped(self):
        source = """<!doctype html>
<html><head><title>Mixed Article</title></head><body>
<article class="content">
<div>
Loose intro text has enough words to deserve its own paragraph in the readable output.
<p>The real paragraph remains in place and still has useful article words.</p>
Loose ending text should not vanish when the div also contains block children.
</div>
</article>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=80).parse()

        self.assertIn("<p>", result["content"])
        self.assertIn("Loose intro text", result["textContent"])
        self.assertIn("The real paragraph remains", result["textContent"])
        self.assertIn("Loose ending text", result["textContent"])

    def test_simplifies_needless_nested_wrappers(self):
        source = """<!doctype html>
<html><head><title>Nested Article</title></head><body>
<main class="content">
<div><section><div><p>The nested article paragraph has enough useful prose to survive extraction cleanly.</p></div></section></div>
</main>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=70).parse()

        self.assertIn("<p>", result["content"])
        self.assertNotIn("<section><div><p>", result["content"])

    def test_text_content_keeps_block_boundaries(self):
        source = """<!doctype html>
<html><head><title>Spacing Article</title></head><body>
<article class="content">
<p>First paragraph has enough useful words to make it through extraction.</p><p>Second paragraph should not be glued to the first one.</p>
</article>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=80).parse()

        self.assertIn("extraction.\n\nSecond", result["textContent"])
        self.assertNotIn("extraction.Second", result["textContent"])

    def test_removes_duplicate_title_heading_and_controls(self):
        source = """<!doctype html>
<html><head><title>Useful Reader Title | Example</title></head><body>
<article class="content">
<h1>Useful Reader Title</h1>
<button>Subscribe now</button>
<input value="email">
<p>The first article paragraph has enough real prose to survive extraction and scoring.</p>
<p>The second article paragraph has more useful words for the reader output.</p>
</article>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=80).parse()

        self.assertEqual(result["title"], "Useful Reader Title")
        self.assertNotIn("<h1>", result["content"])
        self.assertNotIn("Subscribe now", result["textContent"])
        self.assertIn("first article paragraph", result["textContent"])

    def test_cleans_lower_level_junk_headings(self):
        source = """<!doctype html>
<html><head><title>Heading Article</title></head><body>
<article class="content">
<h3 class="related">More like this</h3>
<h4>x</h4>
<h2>A useful section heading</h2>
<p>The article paragraph has enough useful words to pass extraction and remain readable.</p>
<p>The second paragraph keeps the page over the scoring threshold with normal prose.</p>
</article>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=80).parse()

        self.assertNotIn("More like this", result["textContent"])
        self.assertNotIn("<h4>x</h4>", result["content"])
        self.assertIn("A useful section heading", result["textContent"])

    def test_scores_main_article_container(self):
        source = """<!doctype html>
<html><head><title>Main Article</title></head><body>
<main>
<article>
<p>The article body starts here with enough useful prose for direct article scoring.</p>
<p>The article body continues here with another paragraph that should be extracted.</p>
</article>
</main>
<section class="related"><p>Related links and short junk should not win scoring.</p></section>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=80).parse()

        self.assertIn("article body starts", result["textContent"])
        self.assertNotIn("Related links", result["textContent"])

    def test_retries_after_restoring_page_when_unlikely_filter_fails(self):
        source = """<!doctype html>
<html><head><title>Recovered Article</title></head><body>
<div class="comment">
<p>This real article was unfortunately marked with an unlikely class name, but the relaxed retry should recover it.</p>
<p>The second paragraph gives the article enough length to pass the configured threshold after retrying.</p>
</div>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=120).parse()

        self.assertIn("relaxed retry should recover", result["textContent"])

    def test_keeps_video_iframes_but_removes_junk_iframes(self):
        source = """<!doctype html>
<html><head><title>Video Article</title></head><body>
<article class="content">
<p>The article introduces a useful video with enough surrounding prose to score as readable.</p>
<iframe src="https://www.youtube.com/embed/demo"></iframe>
<iframe src="https://ads.example.com/tracker"></iframe>
<p>The article continues after the video with enough text to keep the article body useful.</p>
</article>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=80).parse()

        self.assertIn("youtube.com/embed/demo", result["content"])
        self.assertNotIn("ads.example.com", result["content"])

    def test_allowed_video_regex_option(self):
        source = """<!doctype html>
<html><head><title>Custom Video Article</title></head><body>
<article class="content">
<p>The article introduces a useful custom video with enough prose to score as readable.</p>
<iframe src="https://video.example.com/embed/demo"></iframe>
<p>The article continues after the video with enough text to keep the article body useful.</p>
</article>
</body></html>"""
        result = Readability(
            parse_document(source),
            char_threshold=80,
            allowed_video_regex=re.compile(r"video\.example\.com"),
        ).parse()

        self.assertIn("video.example.com/embed/demo", result["content"])

    def test_javascript_links_are_unwrapped(self):
        source = """<!doctype html>
<html><head><title>Link Article</title></head><body>
<article class="content">
<p>The article keeps link text even when the href was script based and unusable.</p>
<p><a href="javascript:void(0)">Plain script link</a></p>
<p><a href="javascript:void(0)"><strong>Rich script link</strong></a></p>
<p>The article continues with enough useful prose after those links.</p>
</article>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=80).parse()

        self.assertIn("Plain script link", result["textContent"])
        self.assertIn("<span><strong>Rich script link</strong></span>", result["content"])
        self.assertNotIn("javascript:void", result["content"])

    def test_preserves_semantic_data_tables(self):
        source = """<!doctype html>
<html><head><title>Table Article</title></head><body>
<article class="content">
<p>The article introduces a compact data table with enough surrounding prose to be readable.</p>
<table summary="Quarterly figures">
<caption>Quarterly figures</caption>
<tr><th>Quarter</th><th>Revenue</th></tr>
<tr><td>Q1</td><td>10</td></tr>
</table>
<p>The article continues after the table with enough useful words for extraction.</p>
</article>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=80).parse()

        self.assertIn("<table", result["content"])
        self.assertIn("Quarterly figures", result["textContent"])
        self.assertIn("<th>Quarter</th>", result["content"])

    def test_marks_large_table_from_row_and_colspan_counts(self):
        source = """<!doctype html>
<html><head><title>Large Table Article</title></head><body>
<article class="content">
<p>The article introduces a table whose cell spans make it proper data rather than layout.</p>
<table>
<tr><td colspan="5">Heading</td></tr>
<tr><td rowspan="10">A</td><td>B</td></tr>
</table>
<p>The article continues after the table with enough useful words for extraction.</p>
</article>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=80).parse()

        self.assertIn("<table", result["content"])
        self.assertIn('colspan="5"', result["content"])

    def test_deprecated_size_attrs_removed_from_tables_not_images(self):
        source = ARTICLE.replace(
            '<p>This is the opening paragraph',
            '<table summary="Stats" width="600" height="200">'
            '<tr><th width="100">A</th><td height="20">B</td></tr></table>'
            '<pre width="50">code sample</pre>'
            '<img src="photo.jpg" width="640" height="480" alt="Photo">'
            '<p>This is the opening paragraph',
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertIn('<img src="https://example.com/news/photo.jpg" width="640" height="480"', result["content"])
        self.assertNotIn('<table summary="Stats" width=', result["content"])
        self.assertNotIn('<th width=', result["content"])
        self.assertNotIn('<td height=', result["content"])
        self.assertNotIn('<pre width=', result["content"])

    def test_removes_layout_tables(self):
        source = """<!doctype html>
<html><head><title>Layout Table Article</title></head><body>
<article class="content">
<p>The article has enough proper prose before a layout table that should be removed.</p>
<table role="presentation"><tr><td></td></tr></table>
<p>The article has enough proper prose after the layout table to remain readable.</p>
</article>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=80).parse()

        self.assertNotIn("<table", result["content"])
        self.assertIn("proper prose after", result["textContent"])

    def test_single_cell_table_is_flattened(self):
        source = ARTICLE.replace(
            '<p>This is the opening paragraph',
            '<table><tbody><tr><td>'
            '<p>A single cell table can be flattened into the article without staying a table.</p>'
            '</td></tr></tbody></table>'
            '<p>This is the opening paragraph',
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertNotIn("<table", result["content"])
        self.assertIn("single cell table", result["textContent"])

    def test_recovers_noscript_images(self):
        source = ARTICLE.replace(
            '<p>This is the opening paragraph',
            '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" alt="">'
            '<noscript><img src="photos/from-noscript.jpg" alt="Real image"></noscript>'
            '<p>This is the opening paragraph',
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertIn('src="https://example.com/news/photos/from-noscript.jpg"', result["content"])
        self.assertIn('alt="Real image"', result["content"])
        self.assertNotIn("data:image/gif", result["content"])

    def test_noscript_image_replaces_previous_placeholder_and_keeps_old_url(self):
        source = ARTICLE.replace(
            '<p>This is the opening paragraph',
            '<img src="placeholder.jpg" alt="">'
            '<noscript><img src="photos/from-noscript.jpg" alt="Real image"></noscript>'
            '<p>This is the opening paragraph',
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertIn('src="https://example.com/news/photos/from-noscript.jpg"', result["content"])
        self.assertIn('data-old-src="placeholder.jpg"', result["content"])
        self.assertNotIn('src="https://example.com/news/placeholder.jpg"', result["content"])

    def test_content_browser_uses_recovered_image_not_placeholder(self):
        source = ARTICLE.replace(
            '<p>This is the opening paragraph',
            '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" alt="">'
            '<noscript><img src="photos/from-noscript.jpg" alt="Real image"></noscript>'
            '<p>This is the opening paragraph',
        )
        _title, _items, images, _links, _metadata = extract_content(source, "https://example.com/news/current-story")

        self.assertEqual(images[0]["src"], "https://example.com/news/photos/from-noscript.jpg")

    def test_rejects_non_domonic_input(self):
        with self.assertRaises(TypeError):
            Readability("<p>not parsed</p>")

    def test_honours_max_element_limit(self):
        document = parse_document()
        with self.assertRaises(ValueError):
            Readability(document, max_elems_to_parse=2).parse()

    def test_json_ld_metadata(self):
        source = ARTICLE.replace(
            "</head>",
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"NewsArticle","headline":"JSON-LD title",'
            '"image":{"url":"https://cdn.example.com/lead.jpg"},'
            '"datePublished":"2026-08-30T12:00:00Z",'
            '"dateModified":"2026-08-31T09:00:00Z"}'
            "</script></head>",
        )
        result = Readability(parse_document(source), char_threshold=100).parse()
        self.assertEqual(result["title"], "JSON-LD title")
        self.assertEqual(result["image"], "https://cdn.example.com/lead.jpg")
        self.assertEqual(result["publishedTime"], "2026-08-30T12:00:00Z")
        self.assertEqual(result["modifiedTime"], "2026-08-31T09:00:00Z")

    def test_json_ld_graph_schema_url_and_author_list(self):
        source = ARTICLE.replace(
            "</head>",
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@graph":[{"@type":"BreadcrumbList"},'
            '{"@type":"https://schema.org/NewsArticle",'
            '"headline":"Graph title",'
            '"author":[{"name":"Ada Example"},{"name":"Grace Example"}],'
            '"publisher":{"name":"Example News"}}]}'
            "</script></head>",
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertEqual(result["title"], "Graph title")
        self.assertEqual(result["byline"], "Ada Example, Grace Example")
        self.assertEqual(result["siteName"], "Example News")

    def test_json_ld_prefers_title_that_matches_html_title(self):
        source = ARTICLE.replace(
            "</head>",
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"NewsArticle",'
            '"name":"Example News",'
            '"headline":"A useful article title"}'
            "</script></head>",
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertEqual(result["title"], "A useful article title")

    def test_json_ld_ignores_non_schema_context(self):
        source = ARTICLE.replace(
            "</head>",
            '<script type="application/ld+json">'
            '{"@context":"https://example.com/schema","@type":"NewsArticle",'
            '"headline":"Wrong JSON-LD title"}'
            "</script></head>",
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertEqual(result["title"], "A useful article title")

    def test_detects_and_cleans_inline_byline(self):
        source = ARTICLE.replace(
            '<h1>A useful article title</h1>',
            '<h1>A useful article title</h1><p class="byline">By Ada Inline —</p>',
        ).replace('<meta name="author" content="Ada Example">', "")
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertEqual(result["byline"], "Ada Inline")
        self.assertNotIn("By Ada Inline", result["textContent"])

    def test_byline_prefers_nested_itemprop_name(self):
        source = ARTICLE.replace(
            '<h1>A useful article title</h1>',
            '<h1>A useful article title</h1>'
            '<div class="byline"><span>Profile</span><span itemprop="name">Ada Nested</span></div>',
        ).replace('<meta name="author" content="Ada Example">', "")
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertEqual(result["byline"], "Ada Nested")
        self.assertNotIn("Profile", result["textContent"])

    def test_itemprop_metadata(self):
        source = ARTICLE.replace(
            '<meta name="author" content="Ada Example">',
            '<meta itemprop="author" content="Itemprop Author">'
            '<meta itemprop="datePublished" content="2026-08-31">',
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertEqual(result["byline"], "Itemprop Author")
        self.assertEqual(result["publishedTime"], "2026-08-31")

    def test_cleans_social_metadata(self):
        source = ARTICLE.replace(
            '<meta name="author" content="Ada Example">',
            '<meta property="og:title" content="Social article headline - Example Site">'
            '<meta property="og:image" content="/social.jpg">'
            '<meta name="twitter:description" content="  Social excerpt with   extra spacing.  ">'
            '<meta property="article:author" content="By Social Author">',
        ).replace(
            '<meta name="description" content="A short description of the useful article.">',
            "",
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertEqual(result["title"], "Social article headline")
        self.assertEqual(result["byline"], "Social Author")
        self.assertEqual(result["excerpt"], "Social excerpt with extra spacing.")
        self.assertEqual(result["image"], "https://example.com/social.jpg")

    def test_unescapes_metadata_entities(self):
        source = ARTICLE.replace(
            '<meta name="description" content="A short description of the useful article.">',
            '<meta name="description" content="Tom &amp;amp; Ada &amp;quot;quote&amp;quot;.">',
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertEqual(result["excerpt"], 'Tom & Ada "quote".')

    def test_canonical_uri_and_metadata_aliases(self):
        source = ARTICLE.replace(
            "</head>",
            '<link rel="canonical" href="/canonical-story">'
            '<meta name="sailthru.description" content="Alias excerpt.">'
            '<meta name="sailthru.date" content="2026-08-31">'
            "</head>",
        ).replace(
            '<meta name="description" content="A short description of the useful article.">',
            "",
        )
        document = parse_document(source)
        document.URL = "https://example.com/news/current-story"
        result = Readability(document, char_threshold=100).parse()

        self.assertEqual(result["uri"], "https://example.com/canonical-story")
        self.assertEqual(result["excerpt"], "Alias excerpt.")
        self.assertEqual(result["publishedTime"], "2026-08-31")

    def test_language_and_direction_metadata(self):
        source = ARTICLE.replace(
            '<html lang="en">',
            '<html lang="ar" dir="rtl">',
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertEqual(result["lang"], "ar")
        self.assertEqual(result["dir"], "rtl")

    def test_content_browser_prefers_readability_article(self):
        source = ARTICLE.replace(
            '<p>This is the opening paragraph',
            '<img src="photo.jpg" alt="Useful photo"><p>This is the opening paragraph',
        )
        title, items, images, links, metadata = extract_content(source, "https://example.com/news/current-story")

        self.assertEqual(title, "A useful article title")
        self.assertEqual(metadata["byline"], "Ada Example")
        self.assertEqual(metadata["excerpt"], "A short description of the useful article.")
        self.assertIn("opening paragraph", " ".join(item["text"] for item in items))
        self.assertNotIn("Related stories", " ".join(item["text"] for item in items))
        self.assertEqual(images[0]["src"], "https://example.com/news/photo.jpg")
        self.assertIn("https://example.com/news/sources", [link["href"] for link in links])

    def test_content_browser_keeps_headings_with_following_body(self):
        source = """<!doctype html>
<html><head><title>Ordered Article</title></head><body>
<article class="content">
<h2>First section</h2>
<p>The first section paragraph has enough useful prose to be extracted in order.</p>
<h2>Second section</h2>
<p>The second section paragraph should sit directly after its own heading.</p>
</article>
</body></html>"""
        _title, items, _images, _links, _metadata = extract_content(
            source,
            "https://example.com/ordered",
        )
        labels = [item["text"] for item in items]

        self.assertLess(labels.index("First section"), labels.index("The first section paragraph has enough useful prose to be extracted in order."))
        self.assertLess(labels.index("The first section paragraph has enough useful prose to be extracted in order."), labels.index("Second section"))
        self.assertLess(labels.index("Second section"), labels.index("The second section paragraph should sit directly after its own heading."))

    def test_font_tags_are_replaced_with_spans(self):
        source = ARTICLE.replace(
            "This is the opening paragraph",
            '<font color="red">This is the opening paragraph</font>',
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertIn("<span", result["content"])
        self.assertNotIn("<font", result["content"])

    def test_removes_modal_dialog_content_during_scoring(self):
        source = ARTICLE.replace(
            '<main>',
            '<div aria-modal="true" role="dialog">'
            '<p>This modal text is long enough to score but should never end up in the readable result.</p>'
            '</div><main>',
        )
        result = Readability(parse_document(source), char_threshold=100).parse()

        self.assertNotIn("modal text", result["textContent"])

    def test_promotes_shared_parent_for_close_candidates(self):
        source = """<!doctype html>
<html><head><title>Shared Parent Article</title></head><body>
<main>
<section class="chapter"><p>The first chapter paragraph has enough useful prose to become one candidate in this page.</p></section>
<section class="chapter"><p>The second chapter paragraph has enough useful prose to become another nearby candidate.</p></section>
<section class="chapter"><p>The third chapter paragraph has enough useful prose to persuade the reader to keep their parent.</p></section>
<section class="chapter"><p>The fourth chapter paragraph has enough useful prose and belongs with the rest.</p></section>
</main>
</body></html>"""
        result = Readability(parse_document(source), char_threshold=120).parse()

        self.assertIn("first chapter paragraph", result["textContent"])
        self.assertIn("fourth chapter paragraph", result["textContent"])

    def test_content_browser_uses_readability_lead_image(self):
        source = ARTICLE.replace(
            "</head>",
            '<meta property="og:image" content="/lead.jpg"></head>',
        )
        _title, _items, images, _links, metadata = extract_content(
            source,
            "https://example.com/news/current-story",
        )

        self.assertEqual(images[0]["src"], "https://example.com/lead.jpg")
        self.assertEqual(metadata["image"], "https://example.com/lead.jpg")

    def test_content_browser_extracts_favicon(self):
        source = ARTICLE.replace(
            "</head>",
            '<link rel="shortcut icon" href="/favicon.ico"></head>',
        )
        _title, _items, _images, _links, metadata = extract_content(
            source,
            "https://example.com/news/current-story",
        )

        self.assertEqual(metadata["favicon"], "https://example.com/favicon.ico")

    def test_page_text_exports_readability_metadata(self):
        text = page_text(
            {
                "title": "Example",
                "current_url": "https://example.com/news/story",
                "draft_url": "",
                "metadata": {
                    "byline": "Ada Example",
                    "excerpt": "A short reader summary.",
                    "publishedTime": "2026-08-31",
                    "uri": "https://example.com/news/story",
                },
                "images": [],
                "items": [{"tag": "p", "text": "Article text."}],
                "links": [],
            }
        )

        self.assertIn("# Example", text)
        self.assertIn("By: Ada Example", text)
        self.assertIn("Reader URI: https://example.com/news/story", text)
        self.assertIn("Published: 2026-08-31", text)
        self.assertIn("A short reader summary.", text)
        self.assertIn("## Content", text)

    def test_random_page_button_loads_wikipedia_random(self):
        tab = content_app.current_tab()
        tab["status"] = ""
        original_fetch_url = content_app.fetch_url

        def fake_fetch_url(url, *, incognito=False):
            return ARTICLE, url

        try:
            content_app.fetch_url = fake_fetch_url
            content_app.random_page(None)
        finally:
            content_app.fetch_url = original_fetch_url

        self.assertIn(HOME, tab["status"])

    def test_content_browser_uses_domonic_url_helpers(self):
        self.assertEqual(content_app.normalize_url("example.com"), "https://example.com")
        self.assertEqual(
            content_app.normalize_url("reader mode"),
            "https://www.mojeek.com/search?q=reader+mode",
        )
        self.assertEqual(
            content_app.absolute_url("https://example.com/articles/story", "../image.jpg"),
            "https://example.com/image.jpg",
        )

    def test_content_browser_strips_tracking_params_for_private_loads(self):
        self.assertEqual(
            content_app.strip_tracking_params(
                "https://example.com/story?utm_source=newsletter&a=1&fbclid=abc"
            ),
            "https://example.com/story?a=1",
        )

    def test_content_browser_persists_non_private_state(self):
        original_storage = content_app.browser_storage
        original_tabs = content_app.state["tabs"]
        original_active = content_app.state["active"]
        original_settings = dict(content_app.state["settings"])

        try:
            content_app.browser_storage = Storage()
            content_app.state["tabs"] = []
            content_app.state["active"] = ""
            public_tab = content_app.new_tab_data()
            public_tab["title"] = "Public"
            public_tab["current_url"] = "https://example.com/public"
            private_tab = content_app.new_tab_data(incognito=True)
            private_tab["title"] = "Private"
            private_tab["current_url"] = "https://example.com/private"
            content_app.state["tabs"] = [public_tab, private_tab]
            content_app.state["active"] = private_tab["id"]

            content_app.save_browser_state()
            raw = content_app.browser_storage.getItem("content.state")

            self.assertIn("Public", raw)
            self.assertNotIn("Private", raw)
            self.assertNotIn("https://example.com/private", raw)
            self.assertNotIn(private_tab["id"], raw)
        finally:
            content_app.browser_storage = original_storage
            content_app.state["tabs"] = original_tabs
            content_app.state["active"] = original_active
            content_app.state["settings"] = original_settings

    def test_private_image_node_does_not_auto_load_remote_image(self):
        original = content_app.state["settings"].get("private_load_images", False)
        content_app.state["settings"]["private_load_images"] = False
        html = str(content_app.image_node(
            {"src": "https://example.com/private.jpg", "alt": "Private image"},
            private=True,
        ))
        content_app.state["settings"]["private_load_images"] = original

        self.assertIn("https://example.com/private.jpg", html)
        self.assertNotIn("<img", html)
        self.assertNotIn('src="https://example.com/private.jpg"', html)

    def test_private_image_node_can_be_enabled_explicitly(self):
        original = content_app.state["settings"].get("private_load_images", False)
        try:
            content_app.state["settings"]["private_load_images"] = True
            html = str(content_app.image_node(
                {"src": "https://example.com/private.jpg", "alt": "Private image"},
                private=True,
            ))
        finally:
            content_app.state["settings"]["private_load_images"] = original

        self.assertIn('<img src="https://example.com/private.jpg"', html)

    def test_incognito_fetch_uses_private_headers_and_client(self):
        calls = []
        original_private_session = content_app.private_session

        class Response:
            text = "<html></html>"
            url = "https://example.com/private"

            def raise_for_status(self):
                return None

        class Client:
            def get(self, url, timeout, headers):
                calls.append({"url": url, "timeout": timeout, "headers": headers})
                return Response()

        try:
            content_app.private_session = lambda: Client()
            text, final_url = content_app.fetch_url("https://example.com/private", incognito=True)
        finally:
            content_app.private_session = original_private_session

        self.assertEqual(text, "<html></html>")
        self.assertEqual(final_url, "https://example.com/private")
        self.assertEqual(calls[0]["headers"]["Cookie"], "")
        self.assertEqual(calls[0]["headers"]["Cache-Control"], "no-store")
        self.assertEqual(calls[0]["headers"]["DNT"], "1")
        self.assertEqual(calls[0]["headers"]["Sec-GPC"], "1")

    def test_content_browser_copies_url_to_domonic_clipboard(self):
        tab = content_app.current_tab()
        original_url = tab["current_url"]
        original_draft = tab["draft_url"]
        original_status = tab["status"]
        try:
            tab["current_url"] = "https://example.com/copied"
            content_app.copy_url()
            self.assertEqual(content_app.clipboard.readText(), "https://example.com/copied")
            self.assertEqual(tab["status"], "Copied URL.")
        finally:
            tab["current_url"] = original_url
            tab["draft_url"] = original_draft
            tab["status"] = original_status

    def test_font_settings_are_clamped(self):
        class Target:
            value = "99"

        class Event:
            target = Target()

        content_app.set_ui_font_size(Event())
        content_app.set_reader_font_size(Event())

        self.assertEqual(content_app.state["settings"]["ui_font_size"], 18)
        self.assertEqual(content_app.state["settings"]["reader_font_size"], 24)

        content_app.reset_font_sizes(None)
        self.assertEqual(content_app.state["settings"]["ui_font_size"], 12)
        self.assertEqual(content_app.state["settings"]["reader_font_size"], 16)

    def test_settings_panel_is_hideable(self):
        original = content_app.state["settings"].get("show_settings", False)
        try:
            content_app.state["settings"]["show_settings"] = False
            hidden = str(content_app.index())
            content_app.toggle_settings()
            shown = str(content_app.index())
        finally:
            content_app.state["settings"]["show_settings"] = original

        self.assertIn('title="Settings"', hidden)
        self.assertNotIn('class="settings"', hidden)
        self.assertIn('class="settings"', shown)
        self.assertIn("Load Private Images", shown)

    def test_content_browser_chrome_has_tooltips_and_favicon_slot(self):
        original_tabs = content_app.state["tabs"]
        original_active = content_app.state["active"]
        original_show_settings = content_app.state["settings"].get("show_settings", False)
        try:
            tab = content_app.new_tab_data()
            content_app.state["tabs"] = [tab]
            content_app.state["active"] = tab["id"]
            content_app.state["settings"]["show_settings"] = True
            html = str(content_app.index())
        finally:
            content_app.state["tabs"] = original_tabs
            content_app.state["active"] = original_active
            content_app.state["settings"]["show_settings"] = original_show_settings

        self.assertIn('title="Back"', html)
        self.assertIn('title="Random Wikipedia page"', html)
        self.assertIn('title="Settings"', html)
        self.assertIn('class="settings"', html)
        self.assertIn('class="favicon empty-favicon"', html)

if __name__ == "__main__":
    unittest.main()
