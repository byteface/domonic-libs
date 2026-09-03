"""Tests for the Mermaid port.

Currently: the **sequence-diagram parser + database**. Cases mirror
``packages/mermaid/src/diagrams/sequence/sequenceDiagram.spec.js`` from
mermaid@11.9.0 (vendored under ``tests/fixtures/mermaid/upstream/``), asserting
on the same ``db.get_messages()`` / ``db.get_actors()`` shape the upstream spec
checks. The renderer -- and the domonic SVG / text-metrics work it will drive --
is not ported yet.

``KNOWN_GAPS`` tracks grammar features the hand-written parser does not cover.
"""

import re
import unittest

from domonic_libs.mermaid import detect_type, render, render_element
from domonic_libs.mermaid.pie import parse as parse_pie
from domonic_libs.mermaid.sequence import ParseError, parse, render_sequence
from domonic_libs.mermaid.sequence.db import LINETYPE, PLACEMENT
from domonic_libs.mermaid.flowchart import parse as parse_flow
from domonic_libs.mermaid.timeline import parse as parse_timeline
from domonic_libs.mermaid.text_metrics import (
    calculate_text_dimensions,
    calculate_text_width,
)

KNOWN_GAPS = {
    "sequence parser: stick / reverse-dotted arrow family (-|\\ , //- , ...)",
    "sequence parser: () central connections",
    "sequence parser: box ... end participant grouping",
    "sequence parser: links / link / properties / details JSON payloads",
    "sequence parser: @{ ... } participant config objects",
    "sequence renderer: box participant groups",
    "sequence renderer: autonumber badges, KaTeX, actor-link popups",
    "sequence renderer: label wrapping",
    "pie renderer: HSL-derived theme palette (fixed approximation used)",
    "timeline: bare `period:event` with no space after the colon",
    "diagrams not ported: flowchart, class, state, ER, gantt, gitGraph, journey",
}


def messages(src):
    return parse(src).get_messages()


class TestSequenceBasics(unittest.TestCase):
    def test_basic_definition(self):
        db = parse(
            "sequenceDiagram\n"
            "Alice->Bob:Hello Bob, how are you?\n"
            "Note right of Bob: Bob thinks\n"
            "Bob-->Alice: I am good thanks!"
        )
        actors = db.get_actors()
        self.assertEqual(actors["Alice"]["description"], "Alice")
        msgs = db.get_messages()
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[0]["from"], "Alice")
        self.assertEqual(msgs[2]["from"], "Bob")

    def test_leading_blank_lines_and_comments(self):
        db = parse(
            "\nsequenceDiagram\n"
            "%% a comment\n"
            "# another comment\n"
            "Alice->>Bob: hi\n"
        )
        self.assertEqual(len(db.get_messages()), 1)

    def test_semicolons_as_newlines(self):
        db = parse("sequenceDiagram;Alice->>Bob: hi;Bob-->>Alice: yo")
        self.assertEqual([m["from"] for m in db.get_messages()], ["Alice", "Bob"])

    def test_missing_header_raises(self):
        with self.assertRaises(ParseError):
            parse("Alice->>Bob: hi")


class TestSequenceActors(unittest.TestCase):
    def test_spaces_in_actor_names(self):
        db = parse(
            "sequenceDiagram\n"
            "Alice->>Bob: Looks good?\n"
            "Bob->>Alice: Sure"
        )
        self.assertEqual(list(db.get_actors()), ["Alice", "Bob"])

    def test_dashes_in_actor_names(self):
        db = parse(
            "sequenceDiagram\n"
            "Alice-in-Wonderland->>Bob: hi\n"
            "Bob->>Alice-in-Wonderland: hey"
        )
        self.assertEqual(db.get_actors()["Alice-in-Wonderland"]["description"], "Alice-in-Wonderland")
        self.assertEqual([m["from"] for m in db.get_messages()], ["Alice-in-Wonderland", "Bob"])

    def test_alias_participants(self):
        db = parse(
            "sequenceDiagram\n"
            "participant A as Alice\n"
            "participant B as Bob\n"
            "A->>B: hi\n"
            "B->>A: hey"
        )
        self.assertEqual(db.get_actors()["A"]["description"], "Alice")
        self.assertEqual(db.get_actors()["B"]["description"], "Bob")
        self.assertEqual([m["from"] for m in db.get_messages()], ["A", "B"])

    def test_participant_declaration_order(self):
        db = parse(
            "sequenceDiagram\n"
            "participant Bob\n"
            "participant Alice\n"
            "Alice->>Bob: hi"
        )
        self.assertEqual(list(db.get_actors()), ["Bob", "Alice"])

    def test_actor_keyword(self):
        db = parse("sequenceDiagram\nactor Alice\nAlice->>Bob: hi")
        self.assertEqual(db.get_actors()["Alice"]["type"], "actor")

    def test_actor_renders_as_stick_figure(self):
        out = render("sequenceDiagram\nactor User\nparticipant API\nUser->>API: hi")
        # the actor gets 4 figure limbs (body, arms, 2 legs); the participant a box
        self.assertGreaterEqual(out.count('stroke-width="2" fill="none"'), 4)
        self.assertIn('rx="3" ry="3"', out)


class TestSequenceArrows(unittest.TestCase):
    CASES = {
        "->": LINETYPE["SOLID_OPEN"],
        "-->": LINETYPE["DOTTED_OPEN"],
        "->>": LINETYPE["SOLID"],
        "-->>": LINETYPE["DOTTED"],
        "-x": LINETYPE["SOLID_CROSS"],
        "--x": LINETYPE["DOTTED_CROSS"],
        "-)": LINETYPE["SOLID_POINT"],
        "--)": LINETYPE["DOTTED_POINT"],
        "<<->>": LINETYPE["BIDIRECTIONAL_SOLID"],
        "<<-->>": LINETYPE["BIDIRECTIONAL_DOTTED"],
    }

    def test_every_arrow_maps_to_its_linetype(self):
        for arrow, line_type in self.CASES.items():
            src = f"sequenceDiagram\nAlice{arrow}Bob: msg"
            msgs = messages(src)
            self.assertEqual(msgs[0]["type"], line_type, arrow)
            self.assertEqual(msgs[0]["message"], "msg", arrow)


class TestSequenceActivation(unittest.TestCase):
    def test_explicit_activate_deactivate(self):
        msgs = messages(
            "sequenceDiagram\n"
            "Alice-->>Bob:Hello Bob, how are you?\n"
            "activate Bob\n"
            "Bob-->>Alice:Fine\n"
            "deactivate Bob"
        )
        self.assertEqual(len(msgs), 4)
        self.assertEqual(msgs[0]["type"], LINETYPE["DOTTED"])
        self.assertEqual(msgs[1]["type"], LINETYPE["ACTIVE_START"])
        self.assertEqual(msgs[1]["from"], "Bob")
        self.assertEqual(msgs[3]["type"], LINETYPE["ACTIVE_END"])
        self.assertEqual(msgs[3]["from"], "Bob")

    def test_one_line_activation_notation(self):
        msgs = messages(
            "sequenceDiagram\n"
            "Alice-->>+Bob:Hello\n"
            "Bob-->>- Alice:Hi"
        )
        self.assertEqual(msgs[1]["type"], LINETYPE["ACTIVE_START"])
        self.assertEqual(msgs[1]["from"], "Bob")
        self.assertEqual(msgs[3]["type"], LINETYPE["ACTIVE_END"])
        self.assertEqual(msgs[3]["from"], "Bob")

    def test_deactivating_inactive_participant_raises(self):
        with self.assertRaises(ValueError):
            parse("sequenceDiagram\nAlice-->>Bob: hi\ndeactivate Bob")


class TestSequenceNotesAndTitle(unittest.TestCase):
    def test_note_placements(self):
        msgs = messages(
            "sequenceDiagram\n"
            "Alice->>Bob: hi\n"
            "Note left of Alice: thinking\n"
            "Note right of Bob: waiting\n"
            "Note over Alice,Bob: together"
        )
        notes = [m for m in msgs if m["type"] == LINETYPE["NOTE"]]
        self.assertEqual(notes[0]["placement"], PLACEMENT["LEFTOF"])
        self.assertEqual(notes[1]["placement"], PLACEMENT["RIGHTOF"])
        self.assertEqual(notes[2]["placement"], PLACEMENT["OVER"])
        self.assertEqual(notes[2]["from"], "Alice")
        self.assertEqual(notes[2]["to"], "Bob")

    def test_title_with_colon(self):
        db = parse("sequenceDiagram\ntitle: Diagram Title\nA->>B: x")
        self.assertEqual(db.get_diagram_title(), "Diagram Title")

    def test_title_without_colon(self):
        db = parse("sequenceDiagram\ntitle Diagram Title\nA->>B: x")
        self.assertEqual(db.get_diagram_title(), "Diagram Title")

    def test_acc_title_and_descr(self):
        db = parse(
            "sequenceDiagram\n"
            "accTitle: My Title\n"
            "accDescr: My Description\n"
            "A->>B: x"
        )
        self.assertEqual(db.get_acc_title(), "My Title")
        self.assertEqual(db.get_acc_description(), "My Description")


class TestSequenceNumbersAndBlocks(unittest.TestCase):
    def test_autonumber_off_by_default(self):
        db = parse("sequenceDiagram\nA->>B: x")
        self.assertFalse(db.show_sequence_numbers())

    def test_autonumber_statement_emits_index_message(self):
        msgs = messages("sequenceDiagram\nautonumber\nA->>B: x")
        self.assertEqual(msgs[0]["type"], LINETYPE["AUTONUMBER"])

    def test_autonumber_with_start_and_step(self):
        msgs = messages("sequenceDiagram\nautonumber 10 5\nA->>B: x")
        self.assertEqual(msgs[0]["message"]["start"], 10)
        self.assertEqual(msgs[0]["message"]["step"], 5)

    def test_loop_block(self):
        msgs = messages(
            "sequenceDiagram\n"
            "loop every minute\n"
            "  Alice->>Bob: ping\n"
            "end"
        )
        self.assertEqual(msgs[0]["type"], LINETYPE["LOOP_START"])
        self.assertEqual(msgs[0]["message"], "every minute")
        self.assertEqual(msgs[1]["type"], LINETYPE["SOLID"])
        self.assertEqual(msgs[2]["type"], LINETYPE["LOOP_END"])

    def test_alt_else_block(self):
        msgs = messages(
            "sequenceDiagram\n"
            "alt is sunny\n"
            "  A->>B: go out\n"
            "else is raining\n"
            "  A->>B: stay in\n"
            "end"
        )
        types = [m["type"] for m in msgs]
        self.assertEqual(types[0], LINETYPE["ALT_START"])
        self.assertIn(LINETYPE["ALT_ELSE"], types)
        self.assertEqual(types[-1], LINETYPE["ALT_END"])

    def test_opt_block(self):
        msgs = messages(
            "sequenceDiagram\nopt maybe\n  A->>B: perhaps\nend"
        )
        self.assertEqual(msgs[0]["type"], LINETYPE["OPT_START"])
        self.assertEqual(msgs[-1]["type"], LINETYPE["OPT_END"])

    def test_nested_blocks(self):
        msgs = messages(
            "sequenceDiagram\n"
            "loop outer\n"
            "  alt a\n"
            "    A->>B: x\n"
            "  else b\n"
            "    A->>B: y\n"
            "  end\n"
            "end"
        )
        types = [m["type"] for m in msgs]
        self.assertEqual(types[0], LINETYPE["LOOP_START"])
        self.assertEqual(types[1], LINETYPE["ALT_START"])
        self.assertEqual(types[-1], LINETYPE["LOOP_END"])
        self.assertEqual(types[-2], LINETYPE["ALT_END"])

    def test_unterminated_block_raises(self):
        with self.assertRaises(ParseError):
            parse("sequenceDiagram\nloop forever\n  A->>B: x")


class TestSequenceCreateDestroy(unittest.TestCase):
    def test_create_and_destroy(self):
        db = parse(
            "sequenceDiagram\n"
            "Alice->>Bob: hi\n"
            "create participant Carl\n"
            "Bob->>Carl: hello\n"
            "destroy Carl\n"
            "Carl->>Bob: bye"
        )
        self.assertIn("Carl", db.get_created_actors())
        self.assertIn("Carl", db.get_destroyed_actors())

    def test_create_without_message_raises(self):
        with self.assertRaises(ValueError):
            parse(
                "sequenceDiagram\n"
                "Alice->>Bob: hi\n"
                "create participant Carl\n"
                "Alice->>Bob: not to carl"
            )


class TestPie(unittest.TestCase):
    def test_very_simple_pie(self):
        db = parse_pie('pie\n    "ash" : 100\n')
        self.assertEqual(db.get_sections()["ash"], 100)

    def test_two_sections_and_comment(self):
        db = parse_pie('pie\n%% a comment\n"ash" : 60\n"bat" : 40\n')
        self.assertEqual(db.get_sections(), {"ash": 60, "bat": 40})

    def test_show_data_flag(self):
        db = parse_pie('pie showData\n"ash" : 60\n"bat" : 40\n')
        self.assertTrue(db.get_show_data())

    def test_title_on_header(self):
        db = parse_pie('pie title a 60/40 pie\n"ash" : 60\n"bat" : 40\n')
        self.assertEqual(db.get_diagram_title(), "a 60/40 pie")

    def test_acc_title_and_multiline_descr(self):
        db = parse_pie(
            "pie title a neat chart\n"
            "accTitle: a neat acc title\n"
            "accDescr {\n  a neat description\n  on multiple lines\n}\n"
            '"ash" : 60\n"bat" : 40\n'
        )
        self.assertEqual(db.get_acc_title(), "a neat acc title")
        self.assertIn("multiple lines", db.get_acc_description())

    def test_decimal_value(self):
        db = parse_pie('pie\n"ash" : 60.67\n"bat" : 40\n')
        self.assertEqual(db.get_sections()["ash"], 60.67)

    def test_negative_value_raises(self):
        from domonic_libs.mermaid.pie import ParseError as PieParseError

        with self.assertRaises(PieParseError):
            parse_pie('pie\n"ash" : -60.67\n"bat" : 40\n')

    def test_unsafe_label_raises(self):
        from domonic_libs.mermaid.pie import ParseError as PieParseError

        with self.assertRaises(PieParseError):
            parse_pie('pie title x\n"__proto__" : 386\n')

    def test_render_slices_legend_and_percentages(self):
        out = render('pie title Pets\n  "Dogs" : 386\n  "Cats" : 85\n  "Rats" : 15')
        self.assertTrue(out.startswith("<svg"))
        self.assertEqual(len(re.findall(r'class="pieCircle"', out)), 3)
        self.assertEqual(len(re.findall(r'class="legend"', out)), 3)
        self.assertIn('class="pieTitleText"', out)
        # 386 / (386+85+15) = 79%
        self.assertRegex(out, r'class="slice"[^>]*>79%<')

    def test_show_data_in_legend(self):
        out = render('pie showData\n  "Dogs" : 386\n  "Cats" : 85')
        self.assertIn("Dogs [386]", out)

    def test_detect_type(self):
        self.assertEqual(detect_type("pie\n\"x\" : 1"), "pie")
        self.assertEqual(detect_type("sequenceDiagram\nA->>B: x"), "sequence")


class TestFlowchart(unittest.TestCase):
    def test_header_direction(self):
        self.assertEqual(parse_flow("flowchart LR\n  A --> B").direction, "LR")
        self.assertEqual(parse_flow("graph TD\n  A --> B").direction, "TD")

    def test_node_shapes(self):
        db = parse_flow(
            "flowchart TD\n"
            "  A[square] --> B(round)\n"
            "  B --> C{diamond}\n"
            "  C --> D((circle))\n"
            "  D --> E([stadium])"
        )
        self.assertEqual(db.vertices["A"]["shape"], "square")
        self.assertEqual(db.vertices["B"]["shape"], "round")
        self.assertEqual(db.vertices["C"]["shape"], "diamond")
        self.assertEqual(db.vertices["D"]["shape"], "circle")
        self.assertEqual(db.vertices["E"]["shape"], "stadium")
        self.assertEqual(db.vertices["A"]["text"], "square")

    def test_edge_types_and_labels(self):
        db = parse_flow(
            "flowchart LR\n"
            "  A --> B\n"
            "  A --- C\n"
            "  A -.-> D\n"
            "  A ==> E\n"
            "  A -->|hi| F\n"
            "  A -- yo --> G"
        )
        by_end = {e["end"]: e for e in db.edges}
        self.assertEqual(by_end["B"]["type"], "arrow_point")
        self.assertEqual(by_end["C"]["type"], "arrow_open")
        self.assertEqual(by_end["D"]["stroke"], "dotted")
        self.assertEqual(by_end["E"]["stroke"], "thick")
        self.assertEqual(by_end["F"]["text"], "hi")
        self.assertEqual(by_end["G"]["text"], "yo")

    def test_chaining_and_ampersand(self):
        db = parse_flow("flowchart TD\n  A --> B --> C\n  X & Y --> Z")
        pairs = {(e["start"], e["end"]) for e in db.edges}
        self.assertEqual(pairs, {("A", "B"), ("B", "C"), ("X", "Z"), ("Y", "Z")})

    def test_subgraphs(self):
        db = parse_flow(
            "flowchart TB\n"
            "  subgraph one [First]\n    a1 --> a2\n  end\n"
            "  subgraph two\n    b1 --> b2\n  end\n"
            "  one --> two"
        )
        self.assertEqual([sg["title"] for sg in db.subgraphs], ["First", "two"])
        self.assertIn("a1", db.subgraphs[0]["nodes"])

    def test_render_produces_svg_with_shapes_and_edges(self):
        out = render(
            "flowchart TD\n"
            "  A[Start] --> B{OK?}\n"
            "  B -->|yes| C[Go]\n"
            "  B -->|no| D[Stop]"
        )
        self.assertTrue(out.startswith("<svg"))
        self.assertRegex(out, r'viewBox="0 0 \d+ \d+"')
        self.assertEqual(len(re.findall(r"flow-node-group", out)), 4)
        self.assertEqual(len(re.findall(r'class="flow-edge', out)), 3)
        self.assertIn("<polygon", out)  # the diamond
        self.assertRegex(out, r'class="edge-label">(yes|no)<')
        self.assertIn("marker-end", out)

    def test_render_lr_is_wider_than_tall_relative_to_td(self):
        src = "\n".join(f"  n{i} --> n{i + 1}" for i in range(5))
        td = render_element("flowchart TD\n" + src)
        lr = render_element("flowchart LR\n" + src)
        td_ratio = int(td.getAttribute("width")) / int(td.getAttribute("height"))
        lr_ratio = int(lr.getAttribute("width")) / int(lr.getAttribute("height"))
        self.assertGreater(lr_ratio, td_ratio)


class TestTimeline(unittest.TestCase):
    def test_period_with_single_event(self):
        db = parse_timeline("timeline\n    2002 : LinkedIn\n    2004 : Facebook")
        self.assertEqual([(t["task"], t["events"]) for t in db.get_tasks()],
                         [("2002", ["LinkedIn"]), ("2004", ["Facebook"])])

    def test_period_with_multiple_events(self):
        db = parse_timeline("timeline\n    2004 : Facebook : Google : Flickr")
        self.assertEqual(db.get_tasks()[0]["events"], ["Facebook", "Google", "Flickr"])

    def test_continuation_event_line(self):
        db = parse_timeline("timeline\n    2004 : Facebook\n         : Google")
        self.assertEqual(db.get_tasks()[0]["events"], ["Facebook", "Google"])

    def test_sections_group_tasks(self):
        db = parse_timeline(
            "timeline\n"
            "    section 2021\n      Q1 : a\n      Q2 : b\n"
            "    section 2022\n      Q1 : c"
        )
        self.assertEqual(db.get_sections(), ["2021", "2022"])
        self.assertEqual([t["section"] for t in db.get_tasks()], ["2021", "2021", "2022"])

    def test_title(self):
        db = parse_timeline("timeline\n    title A History\n    2002 : x")
        self.assertEqual(db.get_diagram_title(), "A History")

    def test_render_structure(self):
        out = render(
            "timeline\n    title Roadmap\n"
            "    section Now\n      Parser : sequence : pie\n"
            "    section Next\n      dagre"
        )
        self.assertTrue(out.startswith("<svg"))
        self.assertIn('class="timeline-title"', out)
        self.assertIn('class="activity-line"', out)
        # 2 sections + 2 tasks + 2 events
        self.assertEqual(len(re.findall(r'class="timeline-node', out)), 6)

    def test_detect_type_timeline(self):
        self.assertEqual(detect_type("timeline\n2002 : x"), "timeline")


class TestTextMetrics(unittest.TestCase):
    def test_empty_text_is_zero(self):
        self.assertEqual(calculate_text_dimensions("", {"fontSize": 16}), {"width": 0, "height": 0, "lineHeight": 0})

    def test_width_scales_with_font_size(self):
        small = calculate_text_width("Hello", {"fontSize": 10})
        large = calculate_text_width("Hello", {"fontSize": 20})
        self.assertAlmostEqual(large, small * 2, delta=2)

    def test_bold_is_wider(self):
        regular = calculate_text_width("Participant", {"fontSize": 14, "fontWeight": 400})
        bold = calculate_text_width("Participant", {"fontSize": 14, "fontWeight": 700})
        self.assertGreater(bold, regular)

    def test_multiline_sums_height_takes_max_width(self):
        dims = calculate_text_dimensions("short<br/>a much longer line", {"fontSize": 12})
        one = calculate_text_dimensions("short", {"fontSize": 12})
        self.assertEqual(dims["height"], one["height"] * 2)
        self.assertGreater(dims["width"], one["width"])

    def test_plausible_absolute_width(self):
        # "Alice" in a 14px sans-serif is ~30-36px in a browser.
        self.assertTrue(28 <= calculate_text_width("Alice", {"fontSize": 14}) <= 40)


class TestSequenceRenderer(unittest.TestCase):
    SRC = (
        "sequenceDiagram\n"
        "Alice->>Bob: Hello Bob, how are you?\n"
        "Bob-->>Alice: I am good thanks!\n"
        "Note right of Bob: Bob thinks"
    )

    def test_render_returns_svg_string(self):
        out = render(self.SRC)
        self.assertTrue(out.startswith("<svg"))
        self.assertIn('viewBox="', out)
        self.assertIn("</svg>", out)

    def test_actor_boxes_and_lifelines(self):
        out = render(self.SRC)
        self.assertEqual(out.count('class="actor actor-top"'), 2)
        self.assertEqual(out.count('class="actor actor-bottom"'), 2)  # mirrorActors default
        self.assertEqual(out.count('class="actor-line"'), 2)

    def test_messages_and_note(self):
        out = render(self.SRC)
        self.assertEqual(len(re.findall(r'class="messageText"', out)), 2)
        self.assertIn('class="messageLine1"', out)  # the dotted reply
        self.assertIn('marker-end="url(#arrowhead)"', out)
        self.assertEqual(out.count('class="note"'), 1)
        self.assertIn("Bob thinks", out)

    def test_arrow_marker_defs_present(self):
        out = render(self.SRC)
        self.assertIn('<marker id="arrowhead"', out)
        self.assertIn('<marker id="crosshead"', out)

    def test_self_message_uses_curved_path(self):
        out = render("sequenceDiagram\nAlice->>Alice: think")
        self.assertRegex(out, r"<path[^>]+d=\"M [\d.]+,[\d.]+ C ")

    def test_diagram_grows_with_more_messages(self):
        def height(src):
            el = render_element(src)
            return int(el.getAttribute("height"))

        few = height("sequenceDiagram\nA->>B: one")
        many = height("sequenceDiagram\nA->>B: one\nB->>A: two\nA->>B: three\nB->>A: four")
        self.assertGreater(many, few)


class TestSequenceBlocks(unittest.TestCase):
    def test_loop_box_and_title(self):
        out = render("sequenceDiagram\nloop every day\n  A->>B: ping\nend")
        self.assertEqual(out.count('class="loopLine"'), 4)  # 4 sides
        self.assertIn('class="labelText">loop<', out)
        self.assertIn('class="loopText">every day<', out)

    def test_alt_else_adds_a_section_divider(self):
        out = render(
            "sequenceDiagram\n"
            "alt is ok\n  A->>B: yes\nelse not ok\n  A->>B: no\nend"
        )
        self.assertIn('class="labelText">alt<', out)
        self.assertEqual(out.count('class="loopLine"'), 5)  # 4 sides + 1 divider
        self.assertRegex(out, r'class="loopText">(is ok|not ok)<')

    def test_nested_blocks_render_both_boxes(self):
        out = render(
            "sequenceDiagram\n"
            "loop outer\n  alt a\n    A->>B: x\n  else b\n    A->>B: y\n  end\nend"
        )
        self.assertIn('class="labelText">loop<', out)
        self.assertIn('class="labelText">alt<', out)
        # outer loop box encloses the inner alt box
        self.assertGreaterEqual(out.count('class="loopLine"'), 9)

    def test_rect_block_draws_background(self):
        out = render("sequenceDiagram\nrect rgb(200,200,255)\n  A->>B: x\nend")
        self.assertRegex(out, r'<rect[^>]*class="rect"[^>]*fill="rgb\(200,200,255\)"')

    def test_opt_critical_break_labels(self):
        for keyword, label in (("opt maybe", "opt"), ("critical db", "critical"), ("break oops", "break")):
            out = render(f"sequenceDiagram\n{keyword}\n  A->>B: x\nend")
            self.assertIn(f'class="labelText">{label}<', out)

    def test_block_grows_diagram_height(self):
        plain = int(render_element("sequenceDiagram\nA->>B: x").getAttribute("height"))
        looped = int(
            render_element("sequenceDiagram\nloop forever\n  A->>B: x\nend").getAttribute("height")
        )
        self.assertGreater(looped, plain)


if __name__ == "__main__":
    unittest.main()
