#!/usr/bin/env python3
"""Tests for ccdupe.py. Fixtures live only in temp directories."""

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ccdupe

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "ccdupe.py")


def write(root, rel, data):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(rel) else None
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def build_tree(root):
    """Step-Zero-style tree: equal-size random-ish files, a copy,
    a nested duplicate, a same-size different file, a unique file."""
    write(root, "file1", b"A" * 100)
    write(root, "file2", b"B" * 100)          # same size, diff content
    write(root, "file3", b"C" * 100)
    write(root, "subdir/duplicateoffile1", b"A" * 100)   # dup of file1
    write(root, "subdir/anothersubdir/file21", b"A" * 100)  # dup of file1
    write(root, "unique", b"U" * 37)


@contextlib.contextmanager
def chdir(path):
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


class ListTests(unittest.TestCase):
    def test_recursive_listing_sorted_relative(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            files = ccdupe.collect_files(tmp)
            self.assertEqual(files, [
                "file1", "file2", "file3",
                "subdir/anothersubdir/file21",
                "subdir/duplicateoffile1", "unique",
            ])

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(ccdupe.collect_files(tmp), [])

    def test_cli_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            out = subprocess.run([sys.executable, SCRIPT, "--list", tmp],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0)
            self.assertEqual(out.stdout.splitlines(), [
                "file1", "file2", "file3",
                "subdir/anothersubdir/file21",
                "subdir/duplicateoffile1", "unique",
            ])


class PotentialTests(unittest.TestCase):
    def test_same_size_grouped_unique_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            groups = ccdupe.find_potential(tmp)
            self.assertEqual(groups, [[
                "file1", "file2", "file3",
                "subdir/anothersubdir/file21",
                "subdir/duplicateoffile1",
            ]])

    def test_cli_potential_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            out = subprocess.run([sys.executable, SCRIPT, "--potential", tmp],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0)
            self.assertTrue(out.stdout.startswith("Potential duplicates: "))
            self.assertIn("file1", out.stdout)
            self.assertNotIn("unique", out.stdout)


class ProbableTests(unittest.TestCase):
    def test_same_size_different_content_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            groups = ccdupe.find_probable(tmp)
            self.assertEqual(groups, [[
                "file1", "subdir/anothersubdir/file21",
                "subdir/duplicateoffile1",
            ]])

    def test_cli_probable_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            out = subprocess.run([sys.executable, SCRIPT, "--probable", tmp],
                                 capture_output=True, text=True)
            self.assertEqual(out.stdout.strip(),
                             "Probable duplicates: file1 "
                             "subdir/anothersubdir/file21 "
                             "subdir/duplicateoffile1")


class DuplicateTests(unittest.TestCase):
    def test_confirmed_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            self.assertEqual(ccdupe.find_duplicates(tmp), [[
                "file1", "subdir/anothersubdir/file21",
                "subdir/duplicateoffile1",
            ]])

    def test_no_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a", b"aaa")
            write(tmp, "b", b"bbbb")
            self.assertEqual(ccdupe.find_duplicates(tmp), [])

    def test_multiple_groups_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "x1", b"X" * 10)
            write(tmp, "x2", b"X" * 10)
            write(tmp, "y1", b"Y" * 20)
            write(tmp, "y2", b"Y" * 20)
            self.assertEqual(ccdupe.find_duplicates(tmp),
                             [["x1", "x2"], ["y1", "y2"]])

    def test_md5_collision_still_needs_byte_match(self):
        # Every file reports the same fake MD5; only byte-identical
        # files may be reported.
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a", b"AAAA")
            write(tmp, "b", b"BBBB")  # same size, different bytes
            write(tmp, "c", b"AAAA")
            with mock.patch.object(ccdupe, "file_md5",
                                   return_value="deadbeef"):
                self.assertEqual(ccdupe.find_duplicates(tmp), [["a", "c"]])

    def test_cli_default_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            out = subprocess.run([sys.executable, SCRIPT, tmp],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0)
            self.assertEqual(out.stdout.strip(),
                             "Duplicates: file1 subdir/anothersubdir/file21 "
                             "subdir/duplicateoffile1")

    def test_cli_json_matches_human_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            out = subprocess.run([sys.executable, SCRIPT, "--json", tmp],
                                 capture_output=True, text=True)
            self.assertEqual(json.loads(out.stdout), [[
                "file1", "subdir/anothersubdir/file21",
                "subdir/duplicateoffile1",
            ]])


class MinsizeTests(unittest.TestCase):
    def test_below_threshold_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            self.assertEqual(ccdupe.find_duplicates(tmp, min_size=101), [])

    def test_exact_threshold_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            self.assertEqual(len(ccdupe.find_duplicates(tmp, min_size=100)), 1)

    def test_cli_minsize_1000_prints_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            out = subprocess.run(
                [sys.executable, SCRIPT, "--minsize=1000", tmp],
                capture_output=True, text=True)
            self.assertEqual(out.returncode, 0)
            self.assertEqual(out.stdout, "")


class DeleteTests(unittest.TestCase):
    def test_valid_choice_deletes_exactly_that_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            groups = ccdupe.find_duplicates(tmp)
            with chdir(tmp):
                deleted = ccdupe.prompt_delete(
                    groups, input_fn=lambda: "2", output=lambda *a: None)
            self.assertEqual(deleted, ["subdir/anothersubdir/file21"])
            self.assertFalse(os.path.exists(
                os.path.join(tmp, "subdir/anothersubdir/file21")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "file1")))

    def test_invalid_input_keeps_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            groups = ccdupe.find_duplicates(tmp)
            with chdir(tmp):
                deleted = ccdupe.prompt_delete(
                    groups, input_fn=lambda: "bogus", output=lambda *a: None)
            self.assertEqual(deleted, [])
            for rel in groups[0]:
                self.assertTrue(os.path.exists(os.path.join(tmp, rel)))

    def test_out_of_range_and_empty_keep_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            groups = ccdupe.find_duplicates(tmp)
            for answer in ("99", "", "0"):
                with chdir(tmp):
                    deleted = ccdupe.prompt_delete(
                        groups, input_fn=lambda a=answer: a,
                        output=lambda *a: None)
                self.assertEqual(deleted, [])

    def test_eof_keeps_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            groups = ccdupe.find_duplicates(tmp)

            def boom():
                raise EOFError
            with chdir(tmp):
                deleted = ccdupe.prompt_delete(
                    groups, input_fn=boom, output=lambda *a: None)
            self.assertEqual(deleted, [])

    def test_cli_delete_with_piped_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            out = subprocess.run(
                [sys.executable, SCRIPT, "--delete", tmp],
                input="1\n", capture_output=True, text=True)
            self.assertEqual(out.returncode, 0)
            self.assertIn("Deleted: file1", out.stdout)
            self.assertFalse(os.path.exists(os.path.join(tmp, "file1")))
            self.assertTrue(os.path.exists(
                os.path.join(tmp, "subdir/duplicateoffile1")))

    def test_delete_with_other_modes_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            for mode in ("--list", "--potential", "--probable"):
                out = subprocess.run(
                    [sys.executable, SCRIPT, mode, "--delete", tmp],
                    capture_output=True, text=True)
                self.assertEqual(out.returncode, 2, mode)


class SymlinkTests(unittest.TestCase):
    def test_symlink_to_file_skipped_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "orig", b"Z" * 50)
            os.symlink(os.path.join(tmp, "orig"),
                       os.path.join(tmp, "link"))
            self.assertEqual(ccdupe.collect_files(tmp), ["orig"])
            self.assertEqual(ccdupe.find_duplicates(tmp), [])

    def test_symlink_dir_not_descended_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "real/f", b"Z" * 50)
            os.symlink(os.path.join(tmp, "real"),
                       os.path.join(tmp, "alias"))
            self.assertEqual(ccdupe.collect_files(tmp), ["real/f"])

    def test_follow_symlinks_includes_target_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "orig", b"Z" * 50)
            os.symlink(os.path.join(tmp, "orig"),
                       os.path.join(tmp, "link"))
            groups = ccdupe.find_duplicates(tmp, follow_symlinks=True)
            self.assertEqual(groups, [["link", "orig"]])

    def test_symlink_loop_terminates(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "f", b"Z" * 50)
            os.symlink(tmp, os.path.join(tmp, "loop"))
            files = ccdupe.collect_files(tmp, follow_symlinks=True)
            self.assertEqual(files, ["f"])


class SpecialFileTests(unittest.TestCase):
    def test_empty_files_are_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "e1", b"")
            write(tmp, "e2", b"")
            write(tmp, "nonempty", b"x")
            self.assertEqual(ccdupe.find_duplicates(tmp), [["e1", "e2"]])

    def test_minsize_1_excludes_empty_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "e1", b"")
            write(tmp, "e2", b"")
            self.assertEqual(ccdupe.find_duplicates(tmp, min_size=1), [])

    def test_hardlinks_reported_as_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = write(tmp, "orig", b"H" * 40)
            os.link(src, os.path.join(tmp, "hard"))
            self.assertEqual(ccdupe.find_duplicates(tmp),
                             [["hard", "orig"]])

    def test_unreadable_file_skipped(self):
        if os.geteuid() == 0:
            self.skipTest("running as root: chmod 0 does not block reads")
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a", b"Q" * 30)
            bad = write(tmp, "b", b"Q" * 30)
            os.chmod(bad, 0)
            try:
                self.assertEqual(ccdupe.find_duplicates(tmp), [])
            finally:
                os.chmod(bad, 0o644)

    def test_vanishing_file_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a", b"Q" * 30)
            write(tmp, "b", b"Q" * 30)
            real_md5 = ccdupe.file_md5

            def flaky(path):
                if path.endswith("b"):
                    return None
                return real_md5(path)
            with mock.patch.object(ccdupe, "file_md5", side_effect=flaky):
                self.assertEqual(ccdupe.find_duplicates(tmp), [])


class CliErrorTests(unittest.TestCase):
    def test_missing_directory(self):
        out = subprocess.run([sys.executable, SCRIPT, "/nonexistent-dir-xyz"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)

    def test_file_not_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "f", b"x")
            out = subprocess.run([sys.executable, SCRIPT, path],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 2)

    def test_negative_minsize(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run(
                [sys.executable, SCRIPT, "--minsize", "-5", tmp],
                capture_output=True, text=True)
            self.assertEqual(out.returncode, 2)

    def test_non_integer_minsize(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run(
                [sys.executable, SCRIPT, "--minsize", "abc", tmp],
                capture_output=True, text=True)
            self.assertEqual(out.returncode, 2)

    def test_no_directory_argument(self):
        out = subprocess.run([sys.executable, SCRIPT],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)


if __name__ == "__main__":
    unittest.main()
