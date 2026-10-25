import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "spell_correct.py")
DICT_TEXT = (
    "spelling 100\nmistake 90\nexecution 80\nmechanism 70\n"
    "coding 60\nchallenges 50\n"
)


def run(args, cwd):
    return subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dict_path = os.path.join(self.tmp.name, "dict.txt")
        with open(self.dict_path, "w") as f:
            f.write(DICT_TEXT)

    def tearDown(self):
        self.tmp.cleanup()

    def test_word_mode_page_shape(self):
        result = run(
            [self.dict_path, "speiling", "misteke", "coding", "chalenges"],
            self.tmp.name,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "speiling spelling\nmisteke mistake\ncoding coding\nchalenges challenges\n",
        )

    def test_correct_text(self):
        result = run(
            [self.dict_path, "--correct", "Speiling is a misteke."],
            self.tmp.name,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Spelling is a mistake.\n")

    def test_file_mode(self):
        path = os.path.join(self.tmp.name, "in.txt")
        with open(path, "w") as f:
            f.write("executionw mekanism\n")
        result = run([self.dict_path, "--file", path], self.tmp.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "execution mechanism\n")

    def test_suggestions(self):
        result = run(
            [self.dict_path, "--suggestions", "2", "speiling", "zzzzqqq"],
            self.tmp.name,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "speiling: spelling\nzzzzqqq: \n")

    def test_time_line_format(self):
        result = run(
            [self.dict_path, "--time", "speiling", "coding"], self.tmp.name
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(lines[:2], ["speiling spelling", "coding coding"])
        self.assertRegex(
            lines[2], r"^Time : \d+\.\d+ms \d+\.\d+ words per second$"
        )

    def test_missing_dictionary(self):
        result = run(["/nonexistent/dict.txt", "hello"], self.tmp.name)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr)

    def test_no_words_is_usage_error(self):
        result = run([self.dict_path], self.tmp.name)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage", result.stderr.lower())

    def test_suggestions_with_correct_is_error(self):
        result = run(
            [self.dict_path, "--suggestions", "2", "--correct", "hi"],
            self.tmp.name,
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
