"""Tests for the jq clone. Run from the jq/ directory:

    python3 -m unittest discover -s tests -v
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jq as jqmod  # noqa: E402

JQ_PY = os.path.join(os.path.dirname(__file__), "..", "jq.py")


def run_cli(filter_text, stdin_text, args=()):
    proc = subprocess.run(
        [sys.executable, JQ_PY, *args, filter_text],
        input=stdin_text, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def out(filter_text, stdin_text, args=()):
    code, stdout, _ = run_cli(filter_text, stdin_text, args)
    assert code == 0, (filter_text, stdin_text, code)
    return stdout


class TestPrettyPrint(unittest.TestCase):
    def test_identity_pretty(self):
        self.assertEqual(out(".", '{"b":1,"a":[1,2]}'),
                         '{\n  "b": 1,\n  "a": [\n    1,\n    2\n  ]\n}\n')

    def test_no_filter_is_identity(self):
        self.assertEqual(out(None or ".", '{"a":1}'), '{\n  "a": 1\n}\n')
        proc = subprocess.run([sys.executable, JQ_PY],
                              input='{"a":1}', capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, '{\n  "a": 1\n}\n')

    def test_empty_input_no_output(self):
        self.assertEqual(run_cli(".", "")[0], 0)
        self.assertEqual(run_cli(".", "")[1], "")

    def test_concatenated_documents(self):
        self.assertEqual(out(".+1", "1 2"), "2\n3\n")

    def test_file_input(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            fh.write('{"a": 5}')
            path = fh.name
        try:
            proc = subprocess.run([sys.executable, JQ_PY, ".a", path],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, "5\n")
        finally:
            os.unlink(path)

    def test_empty_containers(self):
        self.assertEqual(out(".", '{"a":[],"b":{}}'),
                         '{\n  "a": [],\n  "b": {}\n}\n')

    def test_number_literals_preserved(self):
        self.assertEqual(out(".", "1.50"), "1.50\n")
        self.assertEqual(out(".", "1.0"), "1.0\n")
        self.assertEqual(out(".", "1e20"), "1E+20\n")
        self.assertEqual(out(".", "123456789012345678901234567890"),
                         "123456789012345678901234567890\n")


class TestPageSteps(unittest.TestCase):
    QUOTES = ('{"quotes":[{"id":1,"quote":"q1","author":"a"},'
              '{"id":2,"quote":"q2","author":"b"}],'
              '"total":100,"skip":0,"limit":2}')

    def test_step2_index(self):
        self.assertEqual(out(".[0]", "[10,20,30]"), "10\n")
        self.assertEqual(out(".[2]", "[10,20,30]"), "30\n")
        self.assertEqual(out(".[-1]", "[10,20,30]"), "30\n")
        self.assertEqual(out(".[9]", "[10,20,30]"), "null\n")

    def test_step3_field_forms(self):
        self.assertTrue(out(".quotes", self.QUOTES).startswith("[\n  {"))
        self.assertEqual(out('.["total"]', self.QUOTES), "100\n")
        self.assertEqual(out(".quotes?", self.QUOTES)[:1], "[")
        self.assertEqual(out('.["quotes"]?', self.QUOTES)[:1], "[")
        self.assertEqual(out(".code", self.QUOTES), "null\n")

    def test_step3_nested(self):
        self.assertEqual(out(".a.b.c", '{"a":{"b":{"c":42}}}'), "42\n")

    def test_step3_optional_suppresses_type_error(self):
        self.assertEqual(out(".a?", "5"), "")
        code, _, _ = run_cli(".a", "5")
        self.assertEqual(code, 5)

    def test_step4_pipe(self):
        self.assertEqual(out(".[0] | .commit.message",
                             '[{"commit":{"message":"hi"}}]'), '"hi"\n')
        self.assertEqual(out(".a, .b | .+10", '{"a":1,"b":2}'), "11\n12\n")
        self.assertEqual(out(".a | .+1, .+2", '{"a":1}'), "2\n3\n")

    def test_step5_collect(self):
        self.assertEqual(out("[.quotes[].quote]", self.QUOTES),
                         '[\n  "q1",\n  "q2"\n]\n')

    def test_iterate_object(self):
        self.assertEqual(out(".[]", '{"a":1,"b":2}'), "1\n2\n")

    def test_field_on_null_is_null(self):
        self.assertEqual(out(".a.b", "null"), "null\n")
        self.assertEqual(out(".[0]", "null"), "null\n")


class TestConstruction(unittest.TestCase):
    def test_array_construction(self):
        self.assertEqual(out("[.a, .b]", '{"a":1,"b":2}'),
                         '[\n  1,\n  2\n]\n')

    def test_object_construction(self):
        self.assertEqual(out("{x: .a, y: .b}", '{"a":1,"b":2}'),
                         '{\n  "x": 1,\n  "y": 2\n}\n')

    def test_object_shorthand(self):
        self.assertEqual(out("{a}", '{"a":7,"b":8}'), '{\n  "a": 7\n}\n')

    def test_object_computed_key(self):
        self.assertEqual(out("{( .k): 1}", '{"k":"v"}'),
                         '{\n  "v": 1\n}\n')

    def test_object_multi_output(self):
        self.assertEqual(out("{a: .[]}", "[1,2]"),
                         '{\n  "a": 1\n}\n{\n  "a": 2\n}\n')

    def test_empty_object(self):
        self.assertEqual(out("{}", '{"a":1}'), "{}\n")


class TestBuiltins(unittest.TestCase):
    def test_select(self):
        self.assertEqual(out("select(. > 1)", "2"), "2\n")
        self.assertEqual(out("select(. > 1)", "1"), "")
        self.assertEqual(out("select(.[] > 1)", "[1,2]"), "[\n  1,\n  2\n]\n")
        self.assertEqual(out(".[] | select(. % 2 == 0)", "[1,2,3,4]"),
                         "2\n4\n")

    def test_map(self):
        self.assertEqual(out("map(.+1)", "[1,2]"), '[\n  2,\n  3\n]\n')
        self.assertEqual(out("map(.a)", '[{"a":1},{"a":2}]'),
                         '[\n  1,\n  2\n]\n')

    def test_length(self):
        self.assertEqual(out("length", '"abc"'), "3\n")
        self.assertEqual(out("length", "[1,2]"), "2\n")
        self.assertEqual(out("length", '{"a":1,"b":2}'), "2\n")
        self.assertEqual(out("length", "null"), "0\n")
        self.assertEqual(out("length", "-5"), "5\n")

    def test_keys(self):
        self.assertEqual(out("keys", '{"b":1,"a":2}'),
                         '[\n  "a",\n  "b"\n]\n')
        self.assertEqual(out("keys", '["x","y"]'), '[\n  0,\n  1\n]\n')

    def test_type(self):
        for doc, want in [("null", '"null"'), ("true", '"boolean"'),
                          ("1", '"number"'), ('"s"', '"string"'),
                          ("[]", '"array"'), ("{}", '"object"')]:
            self.assertEqual(out("type", doc), want + "\n")

    def test_values(self):
        self.assertEqual(out("values", "null"), "")
        self.assertEqual(out("values", "5"), "5\n")
        self.assertEqual(out("values", '{"a":1}'), "1\n")

    def test_empty_not(self):
        self.assertEqual(out("[empty]", "1"), "[]\n")
        self.assertEqual(out("not", "false"), "true\n")
        self.assertEqual(out("not", "null"), "true\n")
        self.assertEqual(out("not", "0"), "false\n")

    def test_has(self):
        self.assertEqual(out('has("a")', '{"a":1}'), "true\n")
        self.assertEqual(out('has("z")', '{"a":1}'), "false\n")
        self.assertEqual(out("has(1)", "[9,8]"), "true\n")
        self.assertEqual(out("has(5)", "[9,8]"), "false\n")

    def test_tostring_tonumber(self):
        self.assertEqual(out("tostring", "5"), '"5"\n')
        self.assertEqual(out("tostring", '"x"'), '"x"\n')
        self.assertEqual(out("tonumber", '"42"'), "42\n")
        self.assertEqual(run_cli("tonumber", '"x"')[0], 5)


class TestOperators(unittest.TestCase):
    def test_arith_numbers(self):
        self.assertEqual(out(". + 2", "3"), "5\n")
        self.assertEqual(out(". - 2", "3"), "1\n")
        self.assertEqual(out(". * 2", "3"), "6\n")
        self.assertEqual(out(". / 2", "7"), "3.5\n")
        self.assertEqual(out(". / 2", "4"), "2\n")
        self.assertEqual(out(". % 3", "-7"), "-1\n")
        self.assertEqual(out(". % -3", "7"), "1\n")

    def test_plus_string_array_object(self):
        self.assertEqual(out('. + "!"', '"hi"'), '"hi!"\n')
        self.assertEqual(out(". + [3]", "[1,2]"), '[\n  1,\n  2,\n  3\n]\n')
        # Object + is a SHALLOW merge (verified against system jq).
        self.assertEqual(out('. + {"a":{"x":9}}',
                             '{"a":{"x":1,"y":2},"b":1}'),
                         '{\n  "a": {\n    "x": 9\n  },\n  "b": 1\n}\n')
        self.assertEqual(out(". + 1", "null"), "1\n")

    def test_minus_list(self):
        self.assertEqual(out(". - [2]", "[1,2,3]"), '[\n  1,\n  3\n]\n')

    def test_mul_deep_merge_and_repeat(self):
        self.assertEqual(out('. * {"a":{"x":9}}',
                             '{"a":{"x":1,"y":2},"b":1}'),
                         '{\n  "a": {\n    "x": 9,\n    "y": 2\n  },\n  "b": 1\n}\n')
        self.assertEqual(out(". * 3", '"ab"'), '"ababab"\n')

    def test_div_string_split(self):
        self.assertEqual(out('. / ","', '"a,b"'),
                         '[\n  "a",\n  "b"\n]\n')

    def test_comparisons(self):
        self.assertEqual(out(". == 1", "1.0"), "true\n")
        self.assertEqual(out(". != 1", "2"), "true\n")
        self.assertEqual(out(". < 2", "1"), "true\n")
        self.assertEqual(out("null < false", "null"), "true\n")
        self.assertEqual(out("false < true", "null"), "true\n")
        self.assertEqual(out("1 < \"a\"", "null"), "true\n")
        # NOTE: bare [] is iterate in jq, not an empty-array literal;
        # [empty] is the empty array.
        self.assertEqual(out("\"a\" < [empty]", "null"), "true\n")
        self.assertEqual(out("[empty] < {}", "null"), "true\n")

    def test_alt(self):
        self.assertEqual(out(". // 5", "null"), "5\n")
        self.assertEqual(out(". // 5", "false"), "5\n")
        self.assertEqual(out(". // 5", "0"), "0\n")
        self.assertEqual(out("[(false, 5) // 99]", "1"), '[\n  5\n]\n')
        self.assertEqual(out("[(false, null) // 99]", "1"), '[\n  99\n]\n')

    def test_and_or(self):
        self.assertEqual(out("true and false", "null"), "false\n")
        self.assertEqual(out("true or false", "null"), "true\n")
        self.assertEqual(out(". and true", "1"), "true\n")

    def test_comma(self):
        self.assertEqual(out(".a, .b", '{"a":1,"b":2}'), "1\n2\n")


class TestStringsSlicesFlags(unittest.TestCase):
    def test_interpolation(self):
        self.assertEqual(out('"hi \\(.name)!"', '{"name":"bob"}'),
                         '"hi bob!"\n')
        self.assertEqual(out('"\\(.a + .b)"', '{"a":1,"b":2}'), '"3"\n')
        self.assertEqual(out('"\\(.a)"', '{"a":[1,2]}'),
                         '"[1,2]"\n')

    def test_slice(self):
        self.assertEqual(out(".[1:3]", "[1,2,3,4]"), '[\n  2,\n  3\n]\n')
        self.assertEqual(out(".[-2:]", "[1,2,3]"), '[\n  2,\n  3\n]\n')
        self.assertEqual(out(".[1:3]", '"abcdef"'), '"bc"\n')
        self.assertEqual(out(".[1:3]", "null"), "null\n")

    def test_compact(self):
        self.assertEqual(out(".", '{"a":[1,2]}', args=("-c",)),
                         '{"a":[1,2]}\n')

    def test_raw(self):
        self.assertEqual(out(".", '"hi"', args=("-r",)), "hi\n")
        self.assertEqual(out(".", "null", args=("-r",)), "null\n")
        self.assertEqual(out(".", "[1]", args=("-r",)), '[\n  1\n]\n')
        self.assertEqual(out(".", '"hi"', args=("-cr",)), "hi\n")

    def test_sort_keys(self):
        self.assertEqual(out(".", '{"b":1,"a":{"d":4,"c":3}}',
                             args=("--sort-keys",)),
                         '{\n  "a": {\n    "c": 3,\n    "d": 4\n  },\n  "b": 1\n}\n')


class TestErrors(unittest.TestCase):
    def test_bad_json_exit_5(self):
        self.assertEqual(run_cli(".", "not json")[0], 5)
        self.assertEqual(run_cli(".", '{"a":}')[0], 5)
        self.assertEqual(run_cli(".", "[1,]")[0], 5)
        self.assertEqual(run_cli(".", '"unterminated')[0], 5)

    def test_bad_filter_exit_3(self):
        self.assertEqual(run_cli("badfilter(", "1")[0], 3)
        self.assertEqual(run_cli(".a |", "1")[0], 3)
        self.assertEqual(run_cli("def", "1")[0], 3)

    def test_runtime_error_exit_5(self):
        self.assertEqual(run_cli(".+1", '"a"')[0], 5)
        self.assertEqual(run_cli(".a", "5")[0], 5)
        self.assertEqual(run_cli(".[]", "5")[0], 5)
        self.assertEqual(run_cli("./0", "1")[0], 5)

    def test_missing_file_exit_2(self):
        proc = subprocess.run([sys.executable, JQ_PY, ".",
                               "no-such-file-12345.json"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)

    def test_library_parser(self):
        self.assertEqual(jqmod.parse_json_stream('{"a":[1,2.5]}')[0]["a"][1]
                         .value, 2.5)
        with self.assertRaises(jqmod.JsonError):
            jqmod.parse_json_stream('{"a":}')
        with self.assertRaises(jqmod.FilterSyntaxError):
            jqmod.parse_filter(".a |")


@unittest.skipUnless(shutil.which("jq"), "system jq not installed")
class TestAgainstSystemJq(unittest.TestCase):
    """Same input + filter through both binaries; stdout must match."""

    CASES = [
        ('{"a":1}', "."),
        ('{"b":1,"a":[1,2]}', "."),
        ('{"quotes":[{"quote":"q1"},{"quote":"q2"}]}', "[.quotes[].quote]"),
        ('[{"commit":{"message":"m"}}]', ".[0] | .commit.message"),
        ('{"a":1,"b":2}', ".a, .b | .+10"),
        ('[1,2,3,4]', ".[1:3]"),
        ('[1,2,3]', "map(.+1)"),
        ('[1,2,3,4]', ".[] | select(. % 2 == 0)"),
        ('{"a":{"x":1,"y":2},"b":1}', '. + {"a":{"x":9}}'),
        ('{"a":{"x":1,"y":2},"b":1}', '. * {"a":{"x":9}}'),
        ('{"x":[10,20],"y":1}', ".x[.y]"),
        ('null', ". // 5"),
        ('{"name":"bob"}', '"hi \\(.name)!"'),
        ('{"b":1,"a":2}', "."),
        ('1.50', "."),
        ('1e20', "."),
        ('[3,1]', "keys"),
        ('"abc"', "length"),
        ('5', "tostring"),
        ('{"a":1}', ".missing"),
        ('[1,2]', ".[-1]"),
        ('"a,b"', '. / ","'),
        ('7', "./2"),
    ]

    def test_matches_system_jq(self):
        for stdin_text, filt in self.CASES:
            for args in [(), ("-c",), ("-r",), ("--sort-keys",)]:
                ours = subprocess.run([sys.executable, JQ_PY, *args, filt],
                                      input=stdin_text, capture_output=True,
                                      text=True)
                real = subprocess.run(["jq", *args, filt],
                                      input=stdin_text, capture_output=True,
                                      text=True)
                self.assertEqual(ours.returncode, real.returncode,
                                 (stdin_text, filt, args, ours.stderr))
                self.assertEqual(ours.stdout, real.stdout,
                                 (stdin_text, filt, args))


if __name__ == "__main__":
    unittest.main()
