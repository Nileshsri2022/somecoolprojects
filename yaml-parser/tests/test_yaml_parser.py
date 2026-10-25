#!/usr/bin/env python3
"""Tests for yaml_parser.py — challenge steps, scope, and errors."""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yaml_parser import YamlError, parse  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
PARSER = os.path.join(PROJECT, "yaml_parser.py")


def run_cli(args, stdin_text=None):
    return subprocess.run(
        [sys.executable, PARSER] + args,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestStep1SimpleMapping(unittest.TestCase):
    def test_page_example_verbatim(self):
        self.assertEqual(
            parse("name: Coding Challenges\nchallenge:\n  name: YAML Parser\n"),
            {"name": "Coding Challenges", "challenge": {"name": "YAML Parser"}},
        )

    def test_deep_nesting(self):
        self.assertEqual(
            parse("a:\n  b:\n    c:\n      d: 1\n"),
            {"a": {"b": {"c": {"d": 1}}}},
        )

    def test_empty_value_is_null(self):
        self.assertEqual(parse("a:\nb: 2\n"), {"a": None, "b": 2})


class TestStep2Scalars(unittest.TestCase):
    def test_page_example_verbatim(self):
        result = parse(
            "key1: true\nkey2: off\nkey3: null\nkey4: value\n"
            "key5: 101\nkey6: ~\nkey7: 0x12d4\nkey8: 023332\n"
            "key9: .inf\nkey10: .NAN\n"
        )
        self.assertEqual(result["key1"], True)
        self.assertEqual(result["key2"], False)
        self.assertEqual(result["key3"], None)
        self.assertEqual(result["key4"], "value")
        self.assertEqual(result["key5"], 101)
        self.assertEqual(result["key6"], None)
        self.assertEqual(result["key7"], 4820)
        self.assertEqual(result["key8"], 9946)
        self.assertTrue(math.isinf(result["key9"]) and result["key9"] > 0)
        self.assertTrue(math.isnan(result["key10"]))

    def test_boolean_variants(self):
        result = parse(
            "a: yes\nb: NO\nc: On\nd: FALSE\ne: y\nf: n\n"
        )
        self.assertEqual(
            result, {"a": True, "b": False, "c": True, "d": False, "e": True, "f": False}
        )

    def test_null_variants(self):
        self.assertEqual(
            parse("a: Null\nb: NULL\nc: ~\nd:\n"),
            {"a": None, "b": None, "c": None, "d": None},
        )

    def test_numbers(self):
        result = parse(
            "a: -42\nb: +7\nc: 0o17\nd: 0xFF\ne: 3.14\n"
            "f: -0.5\ng: 1e3\nh: -.inf\ni: .nan\nj: 08\n"
        )
        self.assertEqual(result["a"], -42)
        self.assertEqual(result["b"], 7)
        self.assertEqual(result["c"], 15)
        self.assertEqual(result["d"], 255)
        self.assertEqual(result["e"], 3.14)
        self.assertEqual(result["f"], -0.5)
        self.assertEqual(result["g"], 1000.0)
        self.assertTrue(math.isinf(result["h"]) and result["h"] < 0)
        self.assertTrue(math.isnan(result["i"]))
        self.assertEqual(result["j"], 8)  # invalid octal falls back to decimal

    def test_non_numbers_stay_strings(self):
        result = parse("a: 1:30\nb: 2026-10-25\nc: hello world\n")
        self.assertEqual(
            result, {"a": "1:30", "b": "2026-10-25", "c": "hello world"}
        )

    def test_plain_string_hash_kept(self):
        self.assertEqual(parse("a: a#b\n"), {"a": "a#b"})

    def test_plain_string_trimmed(self):
        self.assertEqual(parse("a:   spaced out   \n"), {"a": "spaced out"})


class TestStep3QuotedAndBlocks(unittest.TestCase):
    def test_page_quoted_vs_plain(self):
        result = parse('quoted: "Coding Challenges\\n"\nnon: Coding Challenges\\n\n')
        self.assertEqual(result["quoted"], "Coding Challenges\n")
        self.assertEqual(result["non"], "Coding Challenges\\n")

    def test_double_quote_escapes(self):
        result = parse('a: "tab\\there"\nb: "quote\\"x\\""\nc: "A\\x41"\n')
        self.assertEqual(result["a"], "tab\there")
        self.assertEqual(result["b"], 'quote"x"')
        self.assertEqual(result["c"], "AA")

    def test_single_quoted(self):
        result = parse("a: 'it''s'\nb: 'back\\slash'\n")
        self.assertEqual(result["a"], "it's")
        self.assertEqual(result["b"], "back\\slash")

    def test_quoted_keys(self):
        self.assertEqual(parse('"my key": 1\n\'k\': 2\n'), {"my key": 1, "k": 2})

    def test_folded_page_example(self):
        result = parse(
            "message: >\n"
            "  this is an example from\n"
            "  the YAML parser Coding Challenge\n"
            "  that spans more than\n"
            "  one line\n"
        )
        self.assertEqual(
            result["message"],
            "this is an example from the YAML parser Coding Challenge "
            "that spans more than one line\n",
        )

    def test_folded_strip_and_keep(self):
        self.assertEqual(
            parse("m: >-\n  one\n  two\n"), {"m": "one two"}
        )
        self.assertEqual(
            parse("m: >+\n  one\n\n\n"), {"m": "one\n\n\n"}
        )

    def test_literal_page_example(self):
        result = parse(
            "message: |\n"
            "  this is an example from\n"
            "  the YAML parser Coding Challenge\n"
            "  that spans more than\n"
            "  one line\n"
        )
        self.assertEqual(
            result["message"],
            "this is an example from\nthe YAML parser Coding Challenge\n"
            "that spans more than\none line\n",
        )

    def test_literal_strip(self):
        self.assertEqual(parse("m: |-\n  a\n  b\n"), {"m": "a\nb"})

    def test_block_scalar_keeps_hash_lines(self):
        self.assertEqual(
            parse("m: |\n  # not a comment\n  text # also kept\n"),
            {"m": "# not a comment\ntext # also kept\n"},
        )


class TestStep4Collections(unittest.TestCase):
    def test_block_sequence_page_example(self):
        self.assertEqual(
            parse("key: value\narray:\n - 1\n - 2\ndict:\n  innerkey: innervalue\n"),
            {"key": "value", "array": [1, 2], "dict": {"innerkey": "innervalue"}},
        )

    def test_sequence_flush_with_key(self):
        self.assertEqual(
            parse("array:\n- 1\n- 2\n"), {"array": [1, 2]}
        )

    def test_flow_sequence_page_example(self):
        self.assertEqual(
            parse("key: value\narray: [1, 2]\ndict:\n  innerkey: innervalue\n"),
            {"key": "value", "array": [1, 2], "dict": {"innerkey": "innervalue"}},
        )

    def test_flow_mapping_page_example(self):
        self.assertEqual(
            parse("john: { writes: Coding Challenges, loves: dogs, hates: meetings }\n"),
            {"john": {"writes": "Coding Challenges", "loves": "dogs", "hates": "meetings"}},
        )

    def test_nested_flow(self):
        self.assertEqual(
            parse("a: {b: [1, {c: 2}], d: []}\n"),
            {"a": {"b": [1, {"c": 2}], "d": []}},
        )

    def test_sequence_of_mappings(self):
        self.assertEqual(
            parse("- name: a\n  age: 1\n- name: b\n  age: 2\n"),
            [{"name": "a", "age": 1}, {"name": "b", "age": 2}],
        )

    def test_nested_sequence(self):
        self.assertEqual(parse("a:\n  - 1\n  - - 2\n    - 3\n"), {"a": [1, [2, 3]]})

    def test_top_level_forms(self):
        self.assertEqual(parse("- 1\n- 2\n"), [1, 2])
        self.assertEqual(parse("hello\n"), "hello")
        self.assertEqual(parse("42\n"), 42)
        self.assertIsNone(parse(""))
        self.assertIsNone(parse("\n# only a comment\n"))

    def test_comments(self):
        self.assertEqual(
            parse("# head\na: 1 # trailing\n# mid\nb: 2\n"),
            {"a": 1, "b": 2},
        )

    def test_hash_inside_quotes_not_comment(self):
        self.assertEqual(parse('a: "x # y"\n'), {"a": "x # y"})

    def test_document_markers(self):
        self.assertEqual(parse("---\na: 1\n...\n"), {"a": 1})

    def test_block_scalar_in_sequence(self):
        self.assertEqual(parse("- |\n  line one\n  line two\n"), ["line one\nline two\n"])

    def test_flow_in_sequence_item(self):
        self.assertEqual(parse("- [1, 2]\n- {k: v}\n"), [[1, 2], {"k": "v"}])

    def test_int_keys(self):
        self.assertEqual(parse("101: x\n"), {101: "x"})


class TestStep5Errors(unittest.TestCase):
    def assert_error(self, text):
        with self.assertRaises(YamlError) as ctx:
            parse(text)
        self.assertIsNotNone(ctx.exception.lineno)
        return ctx.exception

    def test_tab_indentation(self):
        self.assert_error("a:\n\tb: 1\n")

    def test_unexpected_indentation(self):
        self.assert_error("a: 1\n   b: 2\n")

    def test_mapping_line_without_colon(self):
        self.assert_error("a: 1\njust a line\n")

    def test_duplicate_key(self):
        self.assert_error("a: 1\na: 2\n")

    def test_unclosed_double_quote(self):
        self.assert_error('a: "open\n')

    def test_unclosed_single_quote(self):
        self.assert_error("a: 'open\n")

    def test_unclosed_flow_sequence(self):
        self.assert_error("a: [1, 2\n")

    def test_unclosed_flow_mapping(self):
        self.assert_error("a: {k: v\n")

    def test_trailing_junk_after_quoted(self):
        self.assert_error('a: "x" junk\n')

    def test_unknown_escape(self):
        self.assert_error('a: "x\\q"\n')

    def test_anchor_rejected(self):
        self.assert_error("a: &anchor 1\n")

    def test_alias_rejected(self):
        self.assert_error("a: *anchor\n")

    def test_tag_rejected(self):
        self.assert_error("a: !!str 1\n")

    def test_directive_rejected(self):
        self.assert_error("%YAML 1.2\na: 1\n")

    def test_second_document_rejected(self):
        self.assert_error("a: 1\n---\nb: 2\n")

    def test_explicit_block_indent_rejected(self):
        self.assert_error("a: |2\n  x\n")

    def test_unindented_block_scalar_is_empty(self):
        # Content not indented past the key is not part of the block.
        self.assertEqual(parse("a: |\nb: 2\n"), {"a": "", "b": 2})


class TestCLI(unittest.TestCase):
    def test_file_prints_page_example_json(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False
        ) as handle:
            handle.write("name: Coding Challenges\nchallenge:\n  name: YAML Parser\n")
            path = handle.name
        try:
            proc = run_cli([path])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(
                json.loads(proc.stdout),
                {"name": "Coding Challenges", "challenge": {"name": "YAML Parser"}},
            )
        finally:
            os.unlink(path)

    def test_stdin(self):
        proc = run_cli([], stdin_text="a: [1, 2]\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {"a": [1, 2]})

    def test_parse_error_exit_code_and_stderr(self):
        proc = run_cli([], stdin_text="a: 1\na: 2\n")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertIn("line", proc.stderr)

    def test_missing_file(self):
        proc = run_cli(["/nonexistent/nope.yaml"])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("nope.yaml", proc.stderr)


if __name__ == "__main__":
    unittest.main()
