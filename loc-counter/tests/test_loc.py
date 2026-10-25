"""Tests for loc.py — temp-directory fixtures with known counts only.

The somecoolprojects tree is never counted as a fixture.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from loc import count_directory, count_file, main, summarize  # noqa: E402


def write(root, relpath, content, binary=False):
    path = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if binary else "w"
    with open(path, mode) as f:
        f.write(content)
    return path


PY_FIXTURE = (
    "# a comment\n"
    "\n"
    "x = 1  # trailing comment\n"
    'y = "# not a comment"\n'
    "print(x + y)\n"
)
# lines 5, blanks 1, comments 1, code 3

C_STEP3 = (
    "// full line\n"
    "int a = 1; // trailing\n"
    "/* single line block */\n"
    "/* block with code */ int b = 2;\n"
    "int c = 3;\n"
)
# lines 5, blanks 0, comments 2, code 3

C_STEP4 = (
    "int x = 0; /* start\n"
    " middle\n"
    " end */\n"
    "int y = 1;\n"
)
# lines 4, blanks 0, comments 2, code 2 (the page's Step 4 example)

C_BLOCK = (
    "int a = 1;\n"
    "/* open\n"
    "inside\n"
    "close */ int b = 2;\n"
)
# lines 4, blanks 0, comments 2 (open, inside), code 2 (first, closing-with-code)

MD_FIXTURE = (
    "# Title\n"
    "\n"
    "```python\n"
    "x = 1\n"
    "```\n"
    "\n"
    "Some prose.\n"
)
# lines 7, blanks 2, comments 0, code 5

TXT_FIXTURE = "hello\n\nworld\n\n"
# lines 4, blanks 2, comments 0, code 2


class TestCountFile(unittest.TestCase):
    def test_python(self):
        with tempfile.TemporaryDirectory() as d:
            fc = count_file(write(d, "a.py", PY_FIXTURE))
            self.assertEqual((fc.lines, fc.blanks, fc.comments, fc.code),
                             (5, 1, 1, 3))
            self.assertEqual(fc.language, "Python")

    def test_c_step3(self):
        with tempfile.TemporaryDirectory() as d:
            fc = count_file(write(d, "a.c", C_STEP3))
            self.assertEqual((fc.lines, fc.blanks, fc.comments, fc.code),
                             (5, 0, 2, 3))

    def test_c_step4_page_example(self):
        with tempfile.TemporaryDirectory() as d:
            fc = count_file(write(d, "a.c", C_STEP4))
            self.assertEqual((fc.lines, fc.blanks, fc.comments, fc.code),
                             (4, 0, 2, 2))

    def test_c_block_closing_line_with_code(self):
        with tempfile.TemporaryDirectory() as d:
            fc = count_file(write(d, "a.c", C_BLOCK))
            self.assertEqual((fc.lines, fc.blanks, fc.comments, fc.code),
                             (4, 0, 2, 2))

    def test_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            fc = count_file(write(d, "a.md", MD_FIXTURE))
            self.assertEqual((fc.lines, fc.blanks, fc.comments, fc.code),
                             (7, 2, 0, 5))

    def test_text(self):
        with tempfile.TemporaryDirectory() as d:
            fc = count_file(write(d, "a.txt", TXT_FIXTURE))
            self.assertEqual((fc.lines, fc.blanks, fc.comments, fc.code),
                             (4, 2, 0, 2))

    def test_unknown_extension_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(count_file(write(d, "a.xyz", "x\n")))

    def test_binary_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(count_file(write(d, "a.py", b"x\x00y\n", binary=True)))

    def test_no_trailing_newline_still_counts_last_line(self):
        with tempfile.TemporaryDirectory() as d:
            fc = count_file(write(d, "a.py", "x = 1"))
            self.assertEqual((fc.lines, fc.blanks, fc.comments, fc.code),
                             (1, 0, 0, 1))

    def test_invariant(self):
        with tempfile.TemporaryDirectory() as d:
            for name, content in (("a.py", PY_FIXTURE), ("b.c", C_STEP4),
                                  ("c.md", MD_FIXTURE), ("e.txt", TXT_FIXTURE)):
                fc = count_file(write(d, name, content))
                self.assertEqual(fc.lines, fc.blanks + fc.comments + fc.code)


class TestCountDirectory(unittest.TestCase):
    def test_recursive_walk_and_totals(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "a.py", PY_FIXTURE)
            write(d, "sub/b.c", C_STEP4)
            write(d, "sub/c.md", MD_FIXTURE)
            write(d, "skip.xyz", "zzz\n")
            write(d, ".hidden.py", PY_FIXTURE)
            write(d, ".git/ignored.py", PY_FIXTURE)
            files = count_directory(d)
            self.assertEqual([f.path for f in files],
                             ["a.py", "sub/b.c", "sub/c.md"])
            languages, total = summarize(files)
            self.assertEqual(total, {"files": 3, "lines": 16, "blanks": 3,
                                     "comments": 3, "code": 10})
            self.assertEqual(languages["Python"]["code"], 3)
            self.assertEqual(languages["C"]["comments"], 2)
            self.assertEqual(languages["Markdown"]["code"], 5)

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            files = count_directory(d)
            self.assertEqual(files, [])
            _, total = summarize(files)
            self.assertEqual(total["files"], 0)
            self.assertEqual(total["lines"], 0)

    def test_single_file_path(self):
        with tempfile.TemporaryDirectory() as d:
            path = write(d, "a.py", PY_FIXTURE)
            files = count_directory(path)
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].code, 3)


class TestCli(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def _tree(self, d):
        write(d, "a.py", PY_FIXTURE)
        write(d, "sub/b.c", C_STEP4)

    def test_default_summary(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            code, out, _ = self._run([d])
            self.assertEqual(code, 0)
            self.assertIn("Python", out)
            self.assertIn("Total", out)
            self.assertIn("9", out)  # total lines: 5 + 4

    def test_files_breakdown(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            code, out, _ = self._run(["--files", d])
            self.assertEqual(code, 0)
            self.assertIn("a.py", out)
            self.assertIn("sub/b.c", out)

    def test_json_agrees_with_library(self):
        with tempfile.TemporaryDirectory() as d:
            self._tree(d)
            code, out, _ = self._run(["--json", d])
            self.assertEqual(code, 0)
            data = json.loads(out)
            self.assertEqual(data["total"]["lines"], 9)
            self.assertEqual(data["total"]["code"], 5)
            self.assertEqual(len(data["files"]), 2)
            self.assertEqual(data["languages"]["Python"]["files"], 1)

    def test_missing_path(self):
        code, _, err = self._run(["/nonexistent-dir-xyz"])
        self.assertNotEqual(code, 0)
        self.assertIn("no such file", err)

    def test_no_arguments(self):
        with self.assertRaises(SystemExit) as ctx:
            self._run([])
        self.assertNotEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
