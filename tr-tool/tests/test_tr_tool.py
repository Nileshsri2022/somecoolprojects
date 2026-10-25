#!/usr/bin/env python3
"""Tests for tr_tool.py.

Most CLI cases are byte-compared against system `tr` (GNU
coreutils) when it is available; those cases skip cleanly when
it is not. Cases where this tool deliberately differs from GNU
(BSD `-u`, message wording) assert this tool's own documented
behaviour instead and are marked as such.
"""

import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "tr_tool.py")
HAS_TR = shutil.which("tr") is not None

sys.path.insert(0, ROOT)
import tr_tool  # noqa: E402


def run_mine(args, data):
    return subprocess.run([sys.executable, TOOL] + args,
                          input=data, capture_output=True)


def run_oracle(args, data):
    return subprocess.run(["tr"] + args, input=data, capture_output=True)


class OracleMixin:
    def assert_oracle(self, args, data):
        """Mine and system tr must agree on stdout and exit code."""
        if not HAS_TR:
            self.skipTest("system tr not available")
        mine = run_mine(args, data)
        ref = run_oracle(args, data)
        self.assertEqual(mine.stdout, ref.stdout,
                         "stdout differs for args %r" % (args,))
        self.assertEqual(mine.returncode, ref.returncode,
                         "exit code differs for args %r "
                         "(mine stderr %r, ref stderr %r)"
                         % (args, mine.stderr, ref.stderr))

    def assert_mine_error(self, args, data=b"hello\n"):
        mine = run_mine(args, data)
        self.assertEqual(mine.returncode, 1, "args %r" % (args,))
        self.assertEqual(mine.stdout, b"")
        self.assertTrue(mine.stderr)


GUTENBERG_3 = (
    b"The Project Gutenberg eBook of The Art of War\n"
    b"This ebook is for the use of anyone anywhere in the United States and\n"
)


class TestPageExamples(unittest.TestCase, OracleMixin):
    def test_step1_single_character(self):
        mine = run_mine(["c", "C"], b"coding challenges\n")
        self.assertEqual(mine.stdout, b"Coding Challenges\n")
        self.assertEqual(mine.returncode, 0)

    def test_step2_range(self):
        mine = run_mine(["A-Z", "a-z"], GUTENBERG_3)
        self.assertEqual(mine.stdout, GUTENBERG_3.lower())
        self.assertEqual(mine.returncode, 0)

    def test_step3_classes(self):
        mine = run_mine(["[:upper:]", "[:lower:]"], GUTENBERG_3)
        self.assertEqual(mine.stdout, GUTENBERG_3.lower())

    def test_step4_delete_word_chars(self):
        # Page's first line, exactly as printed on the page.
        mine = run_mine(["-d", "War"],
                        b"The Project Gutenberg eBook of The Art of War\n")
        self.assertEqual(
            mine.stdout,
            b"The Poject Gutenbeg eBook of The At of \n")

    def test_step4_delete_class(self):
        self.assert_oracle(["-d", "[:upper:]"], GUTENBERG_3)

    def test_step5_squeeze(self):
        mine = run_mine(["-s", "AB"], b"AAABBBCCC")
        self.assertEqual(mine.stdout, b"ABCCC")

    def test_step5_delete_squeeze(self):
        self.assert_oracle(["-ds", "[:alnum:]", "[:space:]"],
                           b"hello  world\nfoo\t\tbar  baz\n")


class TestOracleTranslate(unittest.TestCase, OracleMixin):
    def test_literals(self):
        self.assert_oracle(["abc", "XYZ"], b"abcabcxyz\n")

    def test_range_and_literal_mix(self):
        self.assert_oracle(["a-cx-z", "ABCXYZ"], b"abcxyz\n")

    def test_short_set2_pads_with_last_byte(self):
        self.assert_oracle(["abcd", "XY"], b"abcd\n")

    def test_long_set2_excess_ignored(self):
        self.assert_oracle(["ab", "XYZW"], b"ab\n")

    def test_truncate_set1(self):
        self.assert_oracle(["-t", "abc", "XYZW"], b"abcabc\n")

    def test_truncate_set1_empty_set2(self):
        self.assert_oracle(["-t", "abc", ""], b"abc\n")

    def test_lower_upper_both_directions(self):
        self.assert_oracle(["a-z", "A-Z"], b"Hello World\n")
        self.assert_oracle(["[:lower:]", "[:upper:]"], b"Hello World\n")
        self.assert_oracle(["[:upper:]", "[:lower:]"], b"Hello World\n")

    def test_escapes(self):
        self.assert_oracle(["\\n", " "], b"a\nb\n")
        self.assert_oracle(["\\t", " "], b"a\tb\n")
        self.assert_oracle(["\\040", "_"], b"a b c\n")
        self.assert_oracle(["\\101", "X"], b"AAA\n")
        self.assert_oracle(["\\\\", "/"], b"a\\b\n")

    def test_trailing_backslash_is_literal(self):
        # System tr warns but maps backslash; stdout/exit agree.
        self.assert_oracle(["a\\", "XY"], b"a\\b\n")

    def test_literal_hyphen_positions(self):
        self.assert_oracle(["a-", "XY"], b"a-b-\n")
        self.assert_oracle(["-a", "XY"], b"-a-a\n")
        self.assert_oracle(["a\\-z", "XYZ"], b"a-z\n")

    def test_hyphen_after_class_is_literal(self):
        self.assert_oracle(["[:digit:]-", "X"], b"1-2-3\n")

    def test_complement(self):
        self.assert_oracle(["-c", "a-z", "X"], b"Hello World 123\n")
        self.assert_oracle(["-C", "a-z", "X"], b"Hello World 123\n")

    def test_duplicate_in_string1_last_wins(self):
        self.assert_oracle(["aab", "XYZ"], b"aab\n")
        self.assert_oracle(["aba", "XYZ"], b"aab\n")

    def test_repeat_in_string2(self):
        self.assert_oracle(["ab", "A[Z*2]"], b"aaabbb\n")
        self.assert_oracle(["ab", "A[Z*]"], b"aaabbb\n")
        self.assert_oracle(["ab", "A[Z*0]"], b"aaabbb\n")
        self.assert_oracle(["ab", "A[Z*010]"], b"aaabbb\n")

    def test_repeat_in_string1_explicit_count(self):
        self.assert_oracle(["a[b*2]", "XYZ"], b"abbbxyz\n")

    def test_equivalence(self):
        self.assert_oracle(["[=a=]", "X"], b"aaa bbb\n")
        # Equivalence in string2 when translating is an error
        # in both this tool and system tr.
        self.assert_mine_error(["ab", "[=X=]Y"])

    def test_all_classes_as_string1(self):
        for cls in ("alnum", "alpha", "blank", "cntrl", "digit",
                    "graph", "lower", "print", "punct", "space",
                    "upper", "xdigit"):
            with self.subTest(cls=cls):
                self.assert_oracle(["[:%s:]" % cls, "X"],
                                   b"Hello, World! 123\t\n\x01\x7f")

    def test_dash_dash_operand(self):
        self.assert_oracle(["--", "-a", "b"], b"-a-a-\n")

    def test_delete_dash(self):
        self.assert_oracle(["-d", "-"], b"a-b-c\n")

    def test_long_options(self):
        self.assert_oracle(["--delete", "aeiou"], b"hello world\n")
        self.assert_oracle(["--squeeze-repeats", "ab"],
                           b"aaabbbccc\n")
        self.assert_oracle(["--complement", "a-z", "X"],
                           b"Hello World\n")
        self.assert_oracle(["--truncate-set1", "abc", "XY"],
                           b"abc\n")


class TestOracleDeleteSqueeze(unittest.TestCase, OracleMixin):
    def test_delete_literals_ranges_classes(self):
        self.assert_oracle(["-d", "aeiou"], b"hello world\n")
        self.assert_oracle(["-d", "a-z"], b"Hello World 123\n")
        self.assert_oracle(["-d", "[:digit:]"], b"a1b22c333\n")
        self.assert_oracle(["-d", "[:cntrl:]"],
                           b"a\x00b\x01c\x7fd\n")

    def test_delete_complement(self):
        self.assert_oracle(["-d", "-c", "a-z"], b"Hello World 123\n")
        self.assert_oracle(["-d", "-c", "[:digit:]"], b"a1b2\n")

    def test_squeeze_only(self):
        self.assert_oracle(["-s", "ab"], b"aaabbbccc\n")
        self.assert_oracle(["-s", "[:space:]"],
                           b"a  b\t\tc\n\n\n")

    def test_translate_then_squeeze_uses_set2_as_written(self):
        # Pinned oracle case: padded mapping must NOT join the
        # squeeze set (ABBB, not A).
        self.assert_oracle(["-s", "ab", "A"], b"AAABBB")
        self.assert_oracle(["-s", "a-z", "A"], b"aaabbb")

    def test_delete_squeeze_complement(self):
        self.assert_oracle(["-cds", "[:alnum:]", "[:space:]"],
                           b"hello  world!!\nfoo\tbar\n")
        self.assert_oracle(["-cs", "a-z"], b"aa  bb   cc\n")

    def test_empty_input_all_modes(self):
        for args in (["a", "b"], ["-d", "a"], ["-s", "a"],
                     ["-ds", "a", "b"], ["-s", "a", "b"]):
            with self.subTest(args=args):
                self.assert_oracle(args, b"")


class TestErrors(unittest.TestCase, OracleMixin):
    def test_operand_errors(self):
        for args in ([], ["a"], ["a", "b", "c"], ["-d"],
                     ["-d", "a", "b"], ["-ds", "a"]):
            with self.subTest(args=args):
                self.assert_mine_error(args)
                if HAS_TR:
                    ref = run_oracle(args, b"hello\n")
                    self.assertEqual(ref.returncode, 1)

    def test_set_errors(self):
        for args in (["z-a", "a-z"], ["abc", ""],
                     ["-d", "[:rune:]"], ["-d", "[:foo:]"],
                     ["-d", "[:special:]"], ["a[b*]", "XYZ"],
                     ["-d", "a[b*]"], ["[=ab=]", "X"]):
            with self.subTest(args=args):
                self.assert_mine_error(args)
                if HAS_TR:
                    ref = run_oracle(args, b"hello\n")
                    self.assertEqual(ref.returncode, 1)

    def test_unknown_option(self):
        self.assert_mine_error(["-x", "a", "b"])
        self.assert_mine_error(["--bogus", "a", "b"])

    def test_empty_string1_is_noop_not_error(self):
        # Documented oracle-aligned behaviour (not an error).
        self.assert_oracle(["", "a"], b"hello\n")
        self.assert_oracle(["-d", ""], b"hello\n")
        self.assert_oracle(["-s", ""], b"hello\n")

    def test_u_flag_accepted_noop(self):
        # BSD flag; GNU tr rejects it, so this is a fixed
        # expectation, not an oracle case.
        mine = run_mine(["-u", "a", "b"], b"aaa\n")
        self.assertEqual(mine.stdout, b"bbb\n")
        self.assertEqual(mine.returncode, 0)

    def test_help(self):
        mine = run_mine(["--help"], b"")
        self.assertEqual(mine.returncode, 0)
        self.assertIn(b"Usage", mine.stdout)


class TestUnitParse(unittest.TestCase):
    def test_literals_and_ranges(self):
        self.assertEqual(tr_tool.parse_set(b"a-c"), [97, 98, 99])
        self.assertEqual(tr_tool.parse_set(b"abc"), [97, 98, 99])
        self.assertEqual(tr_tool.parse_set(b"A-Z"),
                         list(range(65, 91)))

    def test_classes(self):
        self.assertEqual(tr_tool.parse_set(b"[:digit:]"),
                         list(range(48, 58)))
        self.assertEqual(tr_tool.parse_set(b"[:blank:]"), [9, 32])
        self.assertEqual(tr_tool.parse_set(b"[:space:]"),
                         [9, 10, 11, 12, 13, 32])

    def test_escapes(self):
        self.assertEqual(tr_tool.parse_set(b"\\n\\t\\\\"), [10, 9, 92])
        self.assertEqual(tr_tool.parse_set(b"\\101"), [65])
        self.assertEqual(tr_tool.parse_set(b"\\a\\b\\f\\v\\r"),
                         [7, 8, 12, 11, 13])
        # Trailing backslash is a literal backslash.
        self.assertEqual(tr_tool.parse_set(b"a\\"), [97, 92])

    def test_hyphen_rules(self):
        self.assertEqual(tr_tool.parse_set(b"-a"), [45, 97])
        self.assertEqual(tr_tool.parse_set(b"a-"), [97, 45])
        self.assertEqual(tr_tool.parse_set(b"a\\-z"), [97, 45, 122])
        # Class, hyphen, single: hyphen stays literal.
        parsed = tr_tool.parse_set(b"[:digit:]-x")
        self.assertEqual(parsed, list(range(48, 58)) + [45, 120])

    def test_repeat_and_equivalence(self):
        self.assertEqual(tr_tool.parse_set(b"a[Z*3]"),
                         [97, 90, 90, 90])
        self.assertEqual(tr_tool.parse_set(b"[x*]"), [("fill", 120)])
        self.assertEqual(tr_tool.parse_set(b"[x*0]"), [("fill", 120)])
        self.assertEqual(tr_tool.parse_set(b"[=a=]"), [97])

    def test_parse_errors(self):
        for spec in (b"z-a", b"[:foo:]", b"[:rune:]", b"[=ab=]"):
            with self.subTest(spec=spec):
                with self.assertRaises(tr_tool.TrError):
                    tr_tool.parse_set(spec)

    def test_resolve_fills(self):
        self.assertEqual(
            tr_tool.resolve_fills([97, ("fill", 90)], 5),
            [97, 90, 90, 90, 90])
        self.assertEqual(
            tr_tool.resolve_fills([97, ("fill", 90)], None), [97, 90])


class TestUnitBuildSqueeze(unittest.TestCase):
    def test_build_padding_truncate_last_wins(self):
        table, _ = tr_tool.build_translation(
            tr_tool.parse_set(b"ab"), tr_tool.parse_set(b"X"),
            False, False)
        self.assertEqual(table[98], ord("X"))  # padded with last byte
        table, _ = tr_tool.build_translation(
            tr_tool.parse_set(b"abc"), tr_tool.parse_set(b"XY"),
            False, True)
        self.assertEqual(table[99], 99)  # truncated: c passes through
        table, _ = tr_tool.build_translation(
            tr_tool.parse_set(b"aab"), tr_tool.parse_set(b"XYZ"),
            False, False)
        self.assertEqual(table[97], ord("Y"))  # last pairing wins

    def test_build_complement_and_fill_in_string1_error(self):
        table, _ = tr_tool.build_translation(
            tr_tool.parse_set(b"a"), tr_tool.parse_set(b"X"),
            True, False)
        self.assertEqual(table[97], 97)  # 'a' itself untouched
        self.assertEqual(table[98], ord("X"))
        with self.assertRaises(tr_tool.TrError):
            tr_tool.build_translation(
                tr_tool.parse_set(b"[x*]"), tr_tool.parse_set(b"Y"),
                False, False)

    def test_squeeze_chunk_and_boundary(self):
        out, prev = tr_tool.squeeze_chunk(b"aaab", {97}, None)
        self.assertEqual((out, prev), (b"ab", 98))
        out, prev = tr_tool.squeeze_chunk(b"aaa", {97}, None)
        self.assertEqual((out, prev), (b"a", 97))
        # Run split across chunks still squeezes to one byte.
        out, prev = tr_tool.squeeze_chunk(b"aaa", {97}, prev)
        self.assertEqual((out, prev), (b"", 97))
        out, prev = tr_tool.squeeze_chunk(b"aab", {97}, prev)
        self.assertEqual((out, prev), (b"b", 98))


class TestBytesAndScale(unittest.TestCase, OracleMixin):
    def test_all_256_bytes(self):
        data = bytes(range(256))
        self.assert_oracle(["a-z", "A-Z"], data)
        self.assert_oracle(["-d", "a-z"], data)
        self.assert_oracle(["-s", "a-z"], data)
        self.assert_oracle(["-d", "[:cntrl:]"], data)
        self.assert_oracle(["-c", "a-z", "X"], data)

    def test_nul_bytes(self):
        self.assert_oracle(["a", "b"], b"a\x00a\x00\n")
        self.assert_oracle(["-d", "a"], b"a\x00a\x00\n")

    def test_chunk_boundary_squeeze(self):
        # Run longer than the 64 KiB chunk size.
        data = b"A" * 200000 + b"B" * 100 + b"A" * 70000
        self.assert_oracle(["-s", "AB"], data)

    def test_large_input_step6(self):
        data = b"Hello World! 123\n" * 80000  # ~1.4 MB
        self.assert_oracle(["[:upper:]", "[:lower:]"], data)
        self.assert_oracle(["-ds", "[:alnum:]", "[:space:]"], data)


if __name__ == "__main__":
    unittest.main()
