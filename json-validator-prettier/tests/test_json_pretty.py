#!/usr/bin/env python3
"""Tests for json_pretty.py. Run from the project directory:

    python3 -m unittest discover -s tests -v
"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json_pretty as jp

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(args, stdin_text=None, cwd=None):
    """Run run() capturing stdout/stderr; return (exit_code, out, err)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = jp.run(args, stdin_text=stdin_text)
    return code, out.getvalue(), err.getvalue()


def run_script(args, stdin_text, cwd=None):
    """Run the real script as a subprocess (covers main()/argparse)."""
    proc = subprocess.run(
        [sys.executable, os.path.join(PROJECT_DIR, "json_pretty.py")] + args,
        input=stdin_text, capture_output=True, text=True, cwd=cwd or PROJECT_DIR)
    return proc.returncode, proc.stdout, proc.stderr


class TestValidatePretty(unittest.TestCase):
    def test_page_valid_example(self):
        text = '{"name": "John", "job": "software engineer", ' \
               '"country": "United Kingdom"}'
        value, error = jp.validate(text)
        self.assertIsNone(error)
        self.assertEqual(
            __import__("json").dumps(value, indent=2, ensure_ascii=False),
            '{\n  "name": "John",\n  "job": "software engineer",\n'
            '  "country": "United Kingdom"\n}')

    def test_page_missing_comma(self):
        text = '{"name": "John" "job": "software engineer"}'
        value, error = jp.validate(text)
        self.assertIsNone(value)
        self.assertIsNotNone(error)
        self.assertEqual(error["line"], 1)
        self.assertIn("delimiter", error["message"])
        code, out, err = run_cli([], stdin_text=text)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("Invalid JSON", err)
        self.assertIn(text, err)
        self.assertIn("^", err)

    def test_page_trailing_comma(self):
        text = '{"name": "John",  "job": "software engineer",}'
        value, error = jp.validate(text)
        self.assertIsNone(value)
        code, out, err = run_cli([], stdin_text=text)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")

    def test_minified_formats(self):
        code, out, err = run_cli([], stdin_text='{"a":[1,2],"b":{"c":3}}')
        self.assertEqual(code, 0)
        self.assertEqual(out, '{\n  "a": [\n    1,\n    2\n  ],\n'
                              '  "b": {\n    "c": 3\n  }\n}\n')

    def test_empty_and_whitespace_invalid(self):
        for text in ("", "   \n\t "):
            value, error = jp.validate(text)
            self.assertIsNone(value)
            self.assertIsNotNone(error)

    def test_nan_infinity_rejected(self):
        for text in ("NaN", "Infinity", "-Infinity", '{"a": NaN}',
                     '[1, Infinity]'):
            value, error = jp.validate(text)
            self.assertIsNone(value, text)
            self.assertIsNotNone(error, text)

    def test_other_invalid_forms(self):
        for text in ("{'a': 1}", '{a: 1}', '{"a": 1,}',
                     '{"a": 1} {"b": 2}', '{"a": /* x */ 1}',
                     '{"a": }', '[1, 2', '{"a": 1'):
            value, error = jp.validate(text)
            self.assertIsNone(value, text)

    def test_top_level_scalars_and_arrays(self):
        for text, expected in (("42", "42\n"), ('"hi"', '"hi"\n'),
                               ("[1, 2]", "[\n  1,\n  2\n]\n")):
            code, out, _ = run_cli([], stdin_text=text)
            self.assertEqual((code, out), (0, expected), text)

    def test_unicode_unescaped(self):
        code, out, _ = run_cli([], stdin_text='{"city": "café"}')
        self.assertEqual(code, 0)
        self.assertIn("café", out)
        self.assertNotIn("\\u", out)

    def test_error_caret_position(self):
        text = '{"a": 1, "b": }'
        _, error = jp.validate(text)
        report = jp.format_error(text, error)
        lines = report.split("\n")
        self.assertTrue(lines[2].endswith("^"))
        self.assertEqual(lines[2].index("^"), error["column"] - 1)


class TestSort(unittest.TestCase):
    def test_page_flat_example(self):
        value, _ = jp.validate('{"zebra": 1, "apple": 2, "banana": 3}')
        self.assertEqual(list(jp.sort_value(value)),
                         ["apple", "banana", "zebra"])

    def test_page_nested_example(self):
        value, _ = jp.validate('{"z": {"b": 1, "a": 2}, '
                               '"a": {"y": 3, "x": 4}}')
        sorted_value = jp.sort_value(value)
        self.assertEqual(list(sorted_value), ["a", "z"])
        self.assertEqual(list(sorted_value["a"]), ["x", "y"])
        self.assertEqual(list(sorted_value["z"]), ["a", "b"])

    def test_array_order_unchanged(self):
        value, _ = jp.validate('{"b": [3, 1, 2], "a": 1}')
        self.assertEqual(jp.sort_value(value)["b"], [3, 1, 2])

    def test_sort_flag_output(self):
        code, out, _ = run_cli(["--sort"],
                               stdin_text='{"zebra": 1, "apple": 2}')
        self.assertEqual(code, 0)
        self.assertEqual(out, '{\n  "apple": 2,\n  "zebra": 1\n}\n')


class TestCompress(unittest.TestCase):
    def test_page_example(self):
        text = '{\n  "name": "John",\n  "message": "Hello World"\n}'
        self.assertEqual(jp.compress_json(text),
                         '{"name":"John","message":"Hello World"}')

    def test_tabs_newlines_removed(self):
        text = '{\n\t"a" :\t [ 1 ,\n 2 ]\n}'
        self.assertEqual(jp.compress_json(text), '{"a":[1,2]}')

    def test_whitespace_in_strings_preserved(self):
        # Backslash escapes inside strings pass through untouched.
        text = '{"msg": "a b\\tc", "nl": "x\\ny"}'
        self.assertEqual(jp.compress_json(text),
                         '{"msg":"a b\\tc","nl":"x\\ny"}')
        # Literal tab/newline inside a string value in the source text.
        text2 = '{"msg": "a b\tc", "nl": "x\ny"}'
        self.assertEqual(jp.compress_json(text2),
                         '{"msg":"a b\tc","nl":"x\ny"}')
        # Escaped quote must not end the string early.
        text3 = '{"msg": "say \\" hi \\" there", "a": 1}'
        self.assertEqual(jp.compress_json(text3),
                         '{"msg":"say \\" hi \\" there","a":1}')

    def test_compress_invalid_fails_first(self):
        code, out, err = run_cli(["--compress"],
                                 stdin_text='{"a": 1,}')
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("Invalid JSON", err)

    def test_spellings_survive_compress(self):
        text = '{"n": 1.50, "u": "\\u0041"}'
        self.assertEqual(jp.compress_json(text), '{"n":1.50,"u":"\\u0041"}')

    def test_compress_flag_and_sort_compress(self):
        code, out, _ = run_cli(["--compress"],
                               stdin_text='{ "b": 1, "a": 2 }')
        self.assertEqual((code, out), (0, '{"b":1,"a":2}\n'))
        code, out, _ = run_cli(["--sort", "--compress"],
                               stdin_text='{ "b": 1, "a": 2 }')
        self.assertEqual((code, out), (0, '{"a":2,"b":1}\n'))


class TestYaml(unittest.TestCase):
    def test_page_simple_object(self):
        value, _ = jp.validate('{"name": "John", "age": 30}')
        self.assertEqual(jp.to_yaml(value), ["name: John", "age: 30"])

    def test_page_nested_array(self):
        value, _ = jp.validate(
            '{"person": {"name": "John", "hobbies": ["reading", "coding"]}}')
        self.assertEqual(jp.to_yaml(value),
                         ["person:", "  name: John", "  hobbies:",
                          "    - reading", "    - coding"])

    def test_page_mixed_types(self):
        value, _ = jp.validate(
            '{"active": true, "count": 0, "message": null, "score": 9.5}')
        self.assertEqual(jp.to_yaml(value),
                         ["active: true", "count: 0", "message: null",
                          "score: 9.5"])

    def test_empty_containers(self):
        value, _ = jp.validate('{"e": {}, "a": []}')
        self.assertEqual(jp.to_yaml(value), ["e: {}", "a: []"])
        self.assertEqual(jp.to_yaml({}), ["{}"])
        self.assertEqual(jp.to_yaml([]), ["[]"])

    def test_array_of_objects_dash_first_key(self):
        value, _ = jp.validate('[{"name": "John", "age": 30}, '
                               '{"name": "Ada", "age": 36}]')
        self.assertEqual(jp.to_yaml(value),
                         ["- name: John", "  age: 30",
                          "- name: Ada", "  age: 36"])

    def test_array_of_objects_indent_4_alignment(self):
        # Continuation keys must align with the first key (dash + 2),
        # not with the indent step, for non-default --indent values.
        value, _ = jp.validate('[{"name": "John", "age": 30}]')
        self.assertEqual(jp.to_yaml(value, step=4),
                         ["- name: John", "  age: 30"])

    def test_quoting_protects_types(self):
        value, _ = jp.validate('{"a": "true", "b": "123", "c": "", '
                               '"d": "yes", "e": "1.5"}')
        self.assertEqual(jp.to_yaml(value),
                         ['a: "true"', 'b: "123"', 'c: ""', 'd: "yes"',
                          'e: "1.5"'])

    def test_quoting_colon_hash_and_plain_words(self):
        value, _ = jp.validate('{"a": "a: b", "b": "x # y", '
                               '"c": "well-known", "d": "don\'t"}')
        lines = jp.to_yaml(value)
        self.assertEqual(lines[0], 'a: "a: b"')
        self.assertEqual(lines[1], 'b: "x # y"')
        self.assertEqual(lines[2], "c: well-known")
        self.assertEqual(lines[3], "d: don't")

    def test_yaml_flag_and_sort_yaml(self):
        code, out, _ = run_cli(["--yaml"],
                               stdin_text='{"name": "John", "age": 30}')
        self.assertEqual((code, out), (0, "name: John\nage: 30\n"))
        code, out, _ = run_cli(["--sort", "--yaml"],
                               stdin_text='{"z": 1, "a": 2}')
        self.assertEqual((code, out), (0, "a: 2\nz: 1\n"))

    def test_yaml_invalid_exits_1(self):
        code, out, err = run_cli(["--yaml"], stdin_text='{"a": }')
        self.assertEqual(code, 1)
        self.assertEqual(out, "")

    def test_nested_list_and_top_scalar(self):
        value, _ = jp.validate('{"m": [[1, 2], [3]]}')
        self.assertEqual(jp.to_yaml(value),
                         ["m:", "  -", "    - 1", "    - 2",
                          "  -", "    - 3"])
        self.assertEqual(jp.to_yaml(42), ["42"])
        self.assertEqual(jp.to_yaml("hi"), ["hi"])


class TestCli(unittest.TestCase):
    def test_stdin_dash_and_file(self):
        code, out, _ = run_cli(["-"], stdin_text='{"a": 1}')
        self.assertEqual(code, 0)
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as handle:
            handle.write('{"a": 1}')
            path = handle.name
        try:
            code, out, _ = run_cli([path])
            self.assertEqual((code, out), (0, '{\n  "a": 1\n}\n'))
        finally:
            os.unlink(path)

    def test_missing_file_exits_2(self):
        code, out, err = run_cli(["/nonexistent/nope.json"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("Error", err)

    def test_check_mode(self):
        code, out, _ = run_cli(["--check"], stdin_text='{"a": 1}')
        self.assertEqual((code, out), (0, "Valid JSON\n"))
        code, out, err = run_cli(["--check"], stdin_text='{"a": }')
        self.assertEqual(code, 1)
        self.assertEqual(out, "")

    def test_indent_option_and_bad_values(self):
        code, out, _ = run_cli(["--indent", "4"], stdin_text='{"a": 1}')
        self.assertEqual((code, out), (0, '{\n    "a": 1\n}\n'))
        for bad in ("0", "9"):
            code, out, err = run_cli(["--indent", bad],
                                     stdin_text='{"a": 1}')
            self.assertEqual(code, 2, bad)

    def test_conflicting_modes_exit_2(self):
        code, out, err = run_cli(["--compress", "--yaml"],
                                 stdin_text='{"a": 1}')
        self.assertEqual(code, 2)
        self.assertEqual(out, "")

    def test_help_and_subprocess(self):
        code, out, err = run_script(["--help"], "")
        self.assertEqual(code, 0)
        self.assertIn("--sort", out)
        self.assertIn("--compress", out)
        self.assertIn("--yaml", out)
        code, out, err = run_script(["--indent", "abc"], '{"a": 1}')
        self.assertEqual(code, 2)
        code, out, err = run_script([], '{"b": 1, "a": 2}')
        self.assertEqual(code, 0)
        self.assertIn('"b": 1', out)
        code, out, err = run_script(["--compress"], '{"a": 1,}')
        self.assertEqual(code, 1)

    def test_single_trailing_newline(self):
        for args in ([], ["--sort"], ["--compress"], ["--yaml"],
                     ["--check"]):
            code, out, _ = run_cli(args, stdin_text='{"b": 1, "a": 2}')
            self.assertEqual(code, 0, args)
            self.assertTrue(out.endswith("\n"), args)
            self.assertFalse(out.endswith("\n\n"), args)


if __name__ == "__main__":
    unittest.main()
