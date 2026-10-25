"""Tests for diff.py — Coding Challenges #13, steps 1-4.

Page cases are used verbatim where the page is unambiguous
(Step 1 strings, Step 2 two-line case); the paragraph case uses
the Step 3 output lines unwrapped, as the page itself notes its
display wraps long lines.
"""

import difflib
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import diff as diffmod

# --- Challenge page paragraph fixture (Step 2 / Step 3) ---
OLD_PARA = [
    "Coding Challenges helps you become a better software engineer through that build real applications.",
    "I share a weekly coding challenge aimed at helping software engineers level up their skills through deliberate practice.",
    "I\u2019ve used or am using these coding challenges as exercises to learn a new programming language or technology.",
    "Each challenge will have you writing a full application or tool. Most of which will be based on real world tools and utilities.",
]
NEW_PARA = [
    "Helping you become a better software engineer through coding challenges that build real applications.",
    "I share a weekly coding challenge aimed at helping software engineers level up their skills through deliberate practice.",
    "These are challenges that I\u2019ve used or am using as exercises to learn a new programming language or technology.",
    "Each challenge will have you writing a full application or tool. Most of which will be based on real world tools and utilities.",
]
EXPECTED_PARA_DIFF = [
    "< Coding Challenges helps you become a better software engineer through that build real applications.",
    "> Helping you become a better software engineer through coding challenges that build real applications.",
    "< I\u2019ve used or am using these coding challenges as exercises to learn a new programming language or technology.",
    "> These are challenges that I\u2019ve used or am using as exercises to learn a new programming language or technology.",
]


def is_subsequence(sub, seq):
    it = iter(seq)
    return all(any(x == y for y in it) for x in sub)


def difflib_diff(old, new):
    """< / > lines derived from difflib opcodes (test oracle only)."""
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new).get_opcodes():
        if tag in ("delete", "replace"):
            out.extend("< " + line for line in old[i1:i2])
        if tag in ("insert", "replace"):
            out.extend("> " + line for line in new[j1:j2])
    return out


def diff_from_lcs(old, new):
    """< / > lines from walking both lists alongside their LCS.

    Note: the page's bare < / > format carries no position
    markers, so a pure insertion cannot be replayed from the
    diff text alone (a trailing insertion and a middle one
    look identical without an anchor). The LCS is that anchor:
    this helper derives the expected diff from the LCS and
    checks diff_lines agrees with it, including its
    prefix/suffix trimming.
    """
    common = diffmod.lcs(old, new)
    out, i, j = [], 0, 0
    for line in common:
        while old[i] != line:
            out.append("< " + old[i])
            i += 1
        while new[j] != line:
            out.append("> " + new[j])
            j += 1
        i += 1
        j += 1
    out.extend("< " + line for line in old[i:])
    out.extend("> " + line for line in new[j:])
    return out


class TestLcsStrings(unittest.TestCase):
    """Step 1 — the page's five cases, plus extras."""

    def test_page_cases(self):
        cases = [
            ("ABCDEF", "ABCDEF", "ABCDEF"),
            ("ABC", "XYZ", ""),
            ("AABCXY", "XYZ", "XY"),
            ("", "", ""),
            ("ABCD", "AC", "AC"),
        ]
        for a, b, expected in cases:
            with self.subTest(a=a, b=b):
                self.assertEqual(diffmod.lcs(a, b), expected)

    def test_one_side_empty(self):
        self.assertEqual(diffmod.lcs("", "ABC"), "")
        self.assertEqual(diffmod.lcs("ABC", ""), "")

    def test_single_char(self):
        self.assertEqual(diffmod.lcs("A", "A"), "A")
        self.assertEqual(diffmod.lcs("A", "B"), "")

    def test_repeated_chars_maximal(self):
        result = diffmod.lcs("AAB", "ABA")
        self.assertEqual(len(result), 2)
        self.assertTrue(is_subsequence(result, "AAB"))
        self.assertTrue(is_subsequence(result, "ABA"))

    def test_reversed(self):
        self.assertEqual(len(diffmod.lcs("ABCDEF", "FEDCBA")), 1)


class TestLcsLines(unittest.TestCase):
    """Step 2 — LCS over arrays of strings."""

    def test_page_two_line_case(self):
        old = ["This is a test which contains:", "this is the lcs"]
        new = ["this is the lcs", "we're testing"]
        self.assertEqual(diffmod.lcs(old, new), ["this is the lcs"])

    def test_page_paragraph_case(self):
        self.assertEqual(diffmod.lcs(OLD_PARA, NEW_PARA), [OLD_PARA[1], OLD_PARA[3]])

    def test_empty_and_identical(self):
        self.assertEqual(diffmod.lcs([], ["a"]), [])
        self.assertEqual(diffmod.lcs(["a", "b"], ["a", "b"]), ["a", "b"])

    def test_no_common_lines(self):
        self.assertEqual(diffmod.lcs(["a", "b"], ["c", "d"]), [])

    def test_duplicate_lines_maximal(self):
        old = ["x", "a", "x", "b"]
        new = ["a", "x", "b", "x"]
        result = diffmod.lcs(old, new)
        self.assertEqual(len(result), 3)
        self.assertTrue(is_subsequence(result, old))
        self.assertTrue(is_subsequence(result, new))


class TestDiffLines(unittest.TestCase):
    """Step 3 — < / > output."""

    def test_page_paragraph_case(self):
        self.assertEqual(diffmod.diff_lines(OLD_PARA, NEW_PARA), EXPECTED_PARA_DIFF)

    def test_identical_is_empty(self):
        self.assertEqual(diffmod.diff_lines(["a", "b"], ["a", "b"]), [])

    def test_empty_sides(self):
        self.assertEqual(diffmod.diff_lines([], ["a", "b"]), ["> a", "> b"])
        self.assertEqual(diffmod.diff_lines(["a", "b"], []), ["< a", "< b"])
        self.assertEqual(diffmod.diff_lines([], []), [])

    def test_insertion_and_deletion_middle(self):
        self.assertEqual(diffmod.diff_lines(["a", "c"], ["a", "b", "c"]), ["> b"])
        self.assertEqual(diffmod.diff_lines(["a", "b", "c"], ["a", "c"]), ["< b"])

    def test_single_line_change(self):
        self.assertEqual(diffmod.diff_lines(["a"], ["b"]), ["< a", "> b"])

    def test_blank_line_is_a_line(self):
        self.assertEqual(diffmod.diff_lines(["a", "", "b"], ["a", "b"]), ["< "])

    def test_diff_matches_lcs_walk(self):
        fixtures = [
            (OLD_PARA, NEW_PARA),
            (["a", "b", "c"], ["a", "x", "c", "d"]),
            (["one", "two"], ["one", "two", "three"]),
            (["one", "two", "three"], ["two"]),
            ([], ["only"]),
            (["only"], []),
            (["x", "a", "x", "b"], ["a", "x", "b", "x"]),
        ]
        for old, new in fixtures:
            with self.subTest(old=old, new=new):
                self.assertEqual(diffmod.diff_lines(old, new), diff_from_lcs(old, new))

    def test_matches_difflib_on_unambiguous_fixtures(self):
        fixtures = [
            (OLD_PARA, NEW_PARA),
            (["a", "b", "c", "d"], ["a", "x", "c", "e"]),
            (["alpha", "beta"], ["alpha", "beta", "gamma"]),
            (["alpha", "beta", "gamma"], ["beta"]),
        ]
        for old, new in fixtures:
            with self.subTest(old=old, new=new):
                self.assertEqual(diffmod.diff_lines(old, new), difflib_diff(old, new))

    def test_lcs_length_matches_difflib_everywhere(self):
        fixtures = [
            (OLD_PARA, NEW_PARA),
            (["x", "a", "x", "b"], ["a", "x", "b", "x"]),
            (["a", "a", "a"], ["a", "a"]),
            ([], []),
        ]
        for old, new in fixtures:
            with self.subTest(old=old, new=new):
                matcher = difflib.SequenceMatcher(a=old, b=new)
                matched = sum(size for _, _, size in matcher.get_matching_blocks())
                self.assertEqual(len(diffmod.lcs(old, new)), matched)

    def test_matches_system_diff_contents(self):
        # GNU groups changes into hunks, so compare the set of
        # changed line contents, not the byte stream (see TEST_PLAN).
        with tempfile.TemporaryDirectory() as tmp:
            old_path = os.path.join(tmp, "old.txt")
            new_path = os.path.join(tmp, "new.txt")
            with open(old_path, "w") as f:
                f.write("\n".join(OLD_PARA) + "\n")
            with open(new_path, "w") as f:
                f.write("\n".join(NEW_PARA) + "\n")
            proc = subprocess.run(["diff", old_path, new_path],
                                  capture_output=True, text=True)
            gnu = {line for line in proc.stdout.splitlines()
                   if line.startswith("< ") or line.startswith("> ")}
            self.assertEqual(set(diffmod.diff_lines(OLD_PARA, NEW_PARA)), gnu)


class TestSplitLines(unittest.TestCase):
    def test_trailing_newline_and_empty(self):
        self.assertEqual(diffmod.split_lines(""), [])
        self.assertEqual(diffmod.split_lines("a\n"), ["a"])
        self.assertEqual(diffmod.split_lines("a"), ["a"])
        self.assertEqual(diffmod.split_lines("a\n\nb\n"), ["a", "", "b"])

    def test_crlf(self):
        self.assertEqual(diffmod.split_lines("a\r\nb\r\n"), ["a", "b"])


class TestCli(unittest.TestCase):
    def run_cli(self, args, files):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, content in files.items():
                path = os.path.join(tmp, name)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                paths.append(path)
            proc = subprocess.run(
                [sys.executable, os.path.join(os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))), "diff.py")]
                + [p if p != "MISSING" else os.path.join(tmp, "nope.txt")
                   for p in args(paths)],
                capture_output=True, text=True)
            return proc

    def test_page_paragraph_cli(self):
        proc = self.run_cli(
            lambda p: p,
            {"old.txt": "\n".join(OLD_PARA) + "\n",
             "new.txt": "\n".join(NEW_PARA) + "\n"})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.splitlines(), EXPECTED_PARA_DIFF)

    def test_identical_cli(self):
        proc = self.run_cli(lambda p: p,
                            {"old.txt": "a\nb\n", "new.txt": "a\nb\n"})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")

    def test_wrong_arg_counts(self):
        script = os.path.join(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))), "diff.py")
        for args in ([], ["only-one"], ["a", "b", "c"]):
            with self.subTest(args=args):
                proc = subprocess.run([sys.executable, script] + args,
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 2)
                self.assertIn("usage", proc.stderr)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.join(tmp, "real.txt")
            with open(real, "w") as f:
                f.write("a\n")
            script = os.path.join(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))), "diff.py")
            proc = subprocess.run(
                [sys.executable, script, real, os.path.join(tmp, "nope.txt")],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("nope.txt", proc.stderr)

    def test_missing_final_newline_is_not_a_difference(self):
        proc = self.run_cli(lambda p: p,
                            {"old.txt": "a\nb\n", "new.txt": "a\nb"})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")

    def test_crlf_vs_lf_is_not_a_difference(self):
        proc = self.run_cli(lambda p: p,
                            {"old.txt": "a\r\nb\r\n", "new.txt": "a\nb\n"})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
