"""Tests for json_parser.py. Run from json-parser/:
python3 -m unittest discover -s tests -v

Two kinds of test: parse() value tests (imported), and CLI
subprocess tests (exit code + message). Expected values are
hand-written, never json.loads.
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from json_parser import JsonError, parse  # noqa: E402

TOOL = os.path.join(os.path.dirname(__file__), "..", "json_parser.py")

VALID = [
    ("step1 empty object", "{}", {}),
    ("step2 string value", '{"key": "value"}', {"key": "value"}),
    ("step2 empty string value",
     '{"key": "value", "key2": ""}', {"key": "value", "key2": ""}),
    ("step3 mixed values",
     '{"key1": true, "key2": false, "key3": null, '
     '"key4": "value", "key5": 101}',
     {"key1": True, "key2": False, "key3": None,
      "key4": "value", "key5": 101}),
    ("step3 numbers", '{"a": 101.5, "b": -0, "c": -12.5e-3, '
     '"d": 1e10, "e": 0, "f": 0.1}',
     {"a": 101.5, "b": 0, "c": -0.0125, "d": 1e10, "e": 0, "f": 0.1}),
    ("step4 nested", '{"key": "value", "key-n": 101, '
     '"key-o": {}, "key-l": []}',
     {"key": "value", "key-n": 101, "key-o": {}, "key-l": []}),
    ("step4 deep", '{"a": [1, 2, {"b": []}]}',
     {"a": [1, 2, {"b": []}]}),
    ("step4 deep arrays", "[[[[1]]]]", [[[[1]]]]),
    ("escapes", r'{"a": "x\"y\\z\/\b\f\n\r\t"}',
     {"a": 'x"y\\z/\b\f\n\r\t'}),
    ("unicode escape", r'{"a": "\u0041"}', {"a": "A"}),
    ("surrogate pair", r'{"a": "\uD83D\uDE00"}', {"a": "\U0001F600"}),
    ("top array", '[1, "a", true, null]', [1, "a", True, None]),
    ("top string", '"hello"', "hello"),
    ("top number", "42", 42),
    ("whitespace around", '  \n\t { "a": 1 } \r\n ', {"a": 1}),
]

INVALID = [
    "empty", "   ", "{", "}", "[", '{"key": "value"',
    '{"key": "value",}', "[1, 2,]", '{"key" "value"}',
    '{"key": }', '{key: "value"}', "{'key': 'value'}",
    '{"key": "value"} extra', "{} {}", '{"a": 1} {"b": 2}',
    "01", "+1", "1.", ".5", "1e", "1e+", "-", "NaN", "Infinity",
    "tru", "truex", "nul", "fals", "True", "NULL",
    '"abc', '{"a": "x\ny"}', r'{"a": "\x"}',
    r'{"a": "\u12"}', r'{"a": "\uZZZZ"}',
    r'{"a": "\uD83D"}', r'{"a": "\uD83Dx"}',
    "[1 2]", '{"a": 1 "b": 2}', '{"a": 1, "a": }',
]


def run_cli(args, stdin_data=None):
    proc = subprocess.run(
        [sys.executable, TOOL, *args],
        input=stdin_data, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


class TestParseValues(unittest.TestCase):
    def test_valid_values(self):
        for name, text, expected in VALID:
            with self.subTest(name=name):
                self.assertEqual(parse(text), expected)

    def test_invalid_raises(self):
        for text in INVALID:
            with self.subTest(text=text):
                with self.assertRaises(JsonError):
                    parse(text)


class TestCli(unittest.TestCase):
    def test_valid_cli(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as f:
            f.write('{"key": "value"}')
            path = f.name
        try:
            code, out, _ = run_cli([path])
            self.assertEqual(code, 0)
            self.assertEqual(out, "Valid JSON\n")
        finally:
            os.unlink(path)

    def test_invalid_cli(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as f:
            f.write('{"key": }')
            path = f.name
        try:
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("Invalid JSON", err)
            self.assertIn("line", err)
        finally:
            os.unlink(path)

    def test_stdin_cli(self):
        code, out, _ = run_cli([], stdin_data='{"a": [1, 2]}')
        self.assertEqual(code, 0)
        self.assertEqual(out, "Valid JSON\n")

    def test_no_json_module_in_tool(self):
        with open(TOOL, encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("import json", source)
        self.assertNotIn("json.loads", source)


if __name__ == "__main__":
    unittest.main()
