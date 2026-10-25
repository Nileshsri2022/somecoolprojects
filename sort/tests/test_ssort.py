"""Tests for ssort.py. Run from sort/:
python3 -m unittest discover -s tests -v

Function tests (each algorithm vs Python sorted()) and
CLI tests (vs system sort under LC_ALL=C, plus random
sort properties and error cases).
"""

import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ssort import ALGORITHMS, dedup, random_sort, sort_lines  # noqa: E402

TOOL = os.path.join(os.path.dirname(__file__), "..", "ssort.py")
SYSTEM_SORT = shutil.which("sort")

WORDS = [b"A", b"ACTUAL", b"AGREE", b"AGREEMENT", b"AND",
         b"apple", b"banana", b"apple", b"A", b"",
         b"a", b"aa", b"ab", b"b", b"10", b"2", b"banana"]

# Deterministic shuffled fixture: 500 distinct words + duplicates.
_rng = random.Random(42)
_shuffled = [f"word{i:04d}".encode() for i in range(500)]
_rng.shuffle(_shuffled)
SHUFFLED = _shuffled + [b"word0007", b"word0420", b"word0007"]


def run_tool(args, stdin=None, env=None):
    proc = subprocess.run(
        [sys.executable, TOOL, *args],
        input=stdin, capture_output=True, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def c_env():
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    return env


def run_system(args, stdin=None):
    proc = subprocess.run(
        [SYSTEM_SORT, *args], input=stdin, capture_output=True,
        env=c_env())
    return proc.returncode, proc.stdout, proc.stderr


class TestAlgorithms(unittest.TestCase):
    def test_each_algorithm_matches_sorted(self):
        cases = [[], [b"only"], sorted(WORDS), list(reversed(sorted(WORDS))),
                 [b"x"] * 5, [b"a", b"aa", b"ab", b"b"],
                 list(WORDS), list(SHUFFLED)]
        for name, func in ALGORITHMS.items():
            for case in cases:
                with self.subTest(algorithm=name, case=case[:3]):
                    self.assertEqual(func(case), sorted(case))

    def test_dedup(self):
        self.assertEqual(dedup([b"a", b"a", b"b", b"b", b"c"]),
                         [b"a", b"b", b"c"])

    def test_random_sort_properties(self):
        lines = [b"a", b"b", b"a", b"c", b"b", b"a"]
        out = random_sort(lines, unique=False)
        self.assertEqual(Counter(out), Counter(lines))
        # Equal lines together: each value occupies one run.
        runs = []
        for line in out:
            if not runs or runs[-1] != line:
                runs.append(line)
        self.assertEqual(sorted(runs), [b"a", b"b", b"c"])
        out_u = random_sort(lines, unique=True)
        self.assertEqual(sorted(out_u), [b"a", b"b", b"c"])
        # Larger fixture: a permutation, not the input order.
        out_big = random_sort(SHUFFLED, unique=False)
        self.assertEqual(Counter(out_big), Counter(SHUFFLED))
        self.assertNotEqual(out_big, SHUFFLED)


@unittest.skipUnless(SYSTEM_SORT, "system sort not available")
class TestCliVsSystem(unittest.TestCase):
    def assert_same(self, args, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "in.txt")
            with open(path, "wb") as f:
                f.write(data)
            ours = run_tool([*args, path])
            theirs = run_system([*args, path])
            self.assertEqual(ours[0], 0)
            self.assertEqual(theirs[0], 0)
            self.assertEqual(ours[1], theirs[1])

    def test_default_matches_system(self):
        self.assert_same([], b"\n".join(WORDS) + b"\n")

    def test_unique_matches_system(self):
        self.assert_same(["-u"], b"\n".join(WORDS) + b"\n")

    def test_each_algorithm_same_output(self):
        data = b"\n".join(WORDS) + b"\n"
        outputs = set()
        for name in ALGORITHMS:
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "in.txt")
                with open(path, "wb") as f:
                    f.write(data)
                code, out, _ = run_tool(["--algorithm", name, path])
                self.assertEqual(code, 0)
                outputs.add(out)
        self.assertEqual(len(outputs), 1)

    def test_stdin_dash_multifile_no_newline(self):
        code, out, _ = run_tool([], stdin=b"b\na\nc\n")
        self.assertEqual((code, out), (0, b"a\nb\nc\n"))
        code, out, _ = run_tool(["-"], stdin=b"b\na\n")
        self.assertEqual(out, b"a\nb\n")
        with tempfile.TemporaryDirectory() as tmp:
            p1 = os.path.join(tmp, "a.txt")
            p2 = os.path.join(tmp, "b.txt")
            with open(p1, "wb") as f:
                f.write(b"c\na\n")
            with open(p2, "wb") as f:
                f.write(b"b\n")
            code, out, _ = run_tool([p1, p2])
            self.assertEqual(out, b"a\nb\nc\n")
        # No trailing newline on input: output still ends with one.
        code, out, _ = run_tool([], stdin=b"b\na")
        self.assertEqual(out, b"a\nb\n")
        code, out, _ = run_tool([], stdin=b"")
        self.assertEqual(out, b"")

    def test_random_cli(self):
        code, out, _ = run_tool(["-R"], stdin=b"b\na\nb\nc\na\n")
        self.assertEqual(code, 0)
        self.assertEqual(Counter(out.split(b"\n")[:-1]),
                         Counter([b"a", b"a", b"b", b"b", b"c"]))
        code, out, _ = run_tool(["-R", "-u"], stdin=b"b\na\nb\nc\na\n")
        self.assertEqual(sorted(out.split(b"\n")[:-1]),
                         [b"a", b"b", b"c"])


class TestCliErrors(unittest.TestCase):
    def test_missing_file_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.txt")
            with open(good, "wb") as f:
                f.write(b"b\na\n")
            code, out, err = run_tool(["/nonexistent-xyz", good])
            self.assertEqual(code, 1)
            self.assertEqual(out, b"a\nb\n")
            self.assertIn(b"nonexistent-xyz", err)


if __name__ == "__main__":
    unittest.main()
