"""Tests for the ``dlx`` command-line front end."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from domonic_libs.cli import main


def run(argv, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    import sys

    old_stdin = sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue(), err.getvalue()


class TestCli(unittest.TestCase):
    def test_no_command_prints_help(self):
        code, out, _ = run([])
        self.assertEqual(code, 0)
        self.assertIn("mermaid", out)

    def test_version(self):
        with self.assertRaises(SystemExit) as cm:
            run(["--version"])
        self.assertEqual(cm.exception.code, 0)

    def test_python_m_entrypoint_delegates(self):
        import runpy
        import sys

        argv = sys.argv
        sys.argv = ["domonic_libs", "--version"]
        try:
            with self.assertRaises(SystemExit) as cm:
                runpy.run_module("domonic_libs", run_name="__main__")
            self.assertEqual(cm.exception.code, 0)
        finally:
            sys.argv = argv

    def test_mermaid_flowchart_to_svg(self):
        code, out, _ = run(["mermaid"], stdin="flowchart TD\n A --> B\n B --> C")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("<svg"))
        self.assertIn("flow-node-group", out)

    def test_mermaid_type_override(self):
        code, out, _ = run(["mermaid", "--type", "pie"], stdin='pie\n "a" : 1\n "b" : 2')
        self.assertEqual(code, 0)
        self.assertIn("pieCircle", out)

    def test_mermaid_list(self):
        code, out, _ = run(["mermaid", "--list"])
        self.assertEqual(code, 0)
        self.assertIn("sequence", out)

    def test_mermaid_bad_input(self):
        code, _, err = run(["mermaid"], stdin="not a diagram")
        self.assertEqual(code, 1)
        self.assertIn("dlx:", err)

    def test_md(self):
        code, out, _ = run(["md"], stdin="# Title\n\nsome *text*")
        self.assertIn("<h1>Title</h1>", out)
        self.assertIn("<em>text</em>", out)

    def test_html2md(self):
        code, out, _ = run(["html2md"], stdin="<h1>T</h1><p><strong>b</strong></p>")
        self.assertIn("# T", out)
        self.assertIn("**b**", out)

    def test_sanitize_strips_scripts(self):
        code, out, err = run(["sanitize", "--report"], stdin="<p onclick='x'>ok<script>e()</script></p>")
        self.assertEqual(out.strip(), "<p>ok</p>")
        self.assertIn("removed", err)

    def test_validate_true_false_exit_codes(self):
        code, out, _ = run(["validate", "isEmail", "ada@example.com"])
        self.assertEqual((code, out.strip()), (0, "true"))
        code, out, _ = run(["validate", "isEmail", "nope"])
        self.assertEqual((code, out.strip()), (1, "false"))

    def test_validate_unknown_check(self):
        code, _, err = run(["validate", "isNotARealCheck", "x"])
        self.assertEqual(code, 2)
        self.assertIn("unknown check", err)

    def test_qs_parse(self):
        code, out, _ = run(["qs", "parse", "a[b]=1&c[]=2&c[]=3"])
        self.assertEqual(json.loads(out), {"a": {"b": "1"}, "c": ["2", "3"]})

    def test_qs_stringify(self):
        code, out, _ = run(["qs", "stringify", '{"a": 1, "b": {"c": 2}}'])
        self.assertIn("a=1", out)
        self.assertIn("b%5Bc%5D=2", out)

    def test_htmlparse_outputs_normalized_html_text_and_stats(self):
        html = "<main><h1>Hello</h1><p>A &amp; B</p></main>"

        code, out, _ = run(["htmlparse"], stdin=html)
        self.assertEqual(code, 0)
        self.assertIn("<main>", out)
        self.assertIn("A & B", out)

        code, out, _ = run(["htmlparse", "--text"], stdin=html)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "HelloA & B")

        code, out, _ = run(["htmlparse", "--stats"], stdin=html)
        self.assertEqual(code, 0)
        stats = json.loads(out)
        self.assertEqual(stats["counts"]["tag"], 3)
        self.assertGreaterEqual(stats["nodes"], 6)

    def test_htmlparse_domonic_backend(self):
        code, out, _ = run(["htmlparse", "--domonic-backend"], stdin="<section><h1>Hi</h1></section>")
        self.assertEqual(code, 0)
        self.assertIn("<section>", out)

    def test_dagre_edge_list_to_svg(self):
        code, out, _ = run(["dagre", "--rankdir", "LR"], stdin="a -> b\na -> c\nb -> d\nc -> d")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("<svg"))
        self.assertEqual(out.count("<rect"), 4)
        self.assertGreaterEqual(out.count("<path"), 4)

    def test_dagre_empty(self):
        code, _, err = run(["dagre"], stdin="\n\n")
        self.assertEqual(code, 1)
        self.assertIn("no nodes", err)


if __name__ == "__main__":
    unittest.main()
