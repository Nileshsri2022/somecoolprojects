#!/usr/bin/env python3
"""Tests for tar_tool.py. Temp directories only."""

import io
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tar_tool  # noqa: E402
from tar_tool import (TarError, build_header, iter_entries,  # noqa: E402
                      parse_header)

TOOL = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tar_tool.py")
HAS_TAR = shutil.which("tar") is not None
FILES = {"file1.txt": b"File 1 contents\n",
         "file2.txt": b"File 2 contents\n",
         "file3.txt": b"File 3 contents\n"}


def run_tool(args, cwd, stdin_data=None):
    return subprocess.run([sys.executable, TOOL] + args, cwd=cwd,
                          input=stdin_data, capture_output=True)


def write_files(root, mapping):
    for name, data in mapping.items():
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True) \
            if os.path.dirname(name) else None
        with open(path, "wb") as fh:
            fh.write(data)


def system_archive(tmp, mapping, name="files.tar"):
    src = os.path.join(tmp, "src")
    os.makedirs(src)
    write_files(src, mapping)
    arc = os.path.join(tmp, name)
    subprocess.run(["tar", "--format=ustar", "-cf", arc]
                   + sorted(mapping), cwd=src, check=True,
                   capture_output=True)
    return arc


class HeaderTests(unittest.TestCase):
    def test_round_trip(self):
        raw = build_header("a/b.txt", 0o644, 1000, 1000, 42,
                           1700000000, "0", uname="u", gname="g")
        self.assertEqual(len(raw), 512)
        self.assertEqual(raw[257:263], b"ustar\x00")
        h = parse_header(raw)
        self.assertEqual((h.name, h.mode, h.uid, h.gid, h.size,
                          h.mtime, h.typeflag, h.uname, h.gname),
                         ("a/b.txt", 0o644, 1000, 1000, 42,
                          1700000000, "0", "u", "g"))

    def test_checksum_detects_corruption(self):
        raw = bytearray(build_header("x.txt", 0o644, 0, 0, 0, 0, "0"))
        raw[10] ^= 0x01
        with self.assertRaises(TarError):
            parse_header(bytes(raw))

    def test_long_name_prefix(self):
        name = "d" * 60 + "/" + "f" * 60 + ".txt"
        self.assertGreater(len(name), 100)
        h = parse_header(build_header(name, 0o644, 0, 0, 0, 0, "0"))
        self.assertEqual(h.name, name)

    def test_name_too_long_raises(self):
        with self.assertRaises(TarError):
            build_header("x" * 300, 0o644, 0, 0, 0, 0, "0")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    @unittest.skipUnless(HAS_TAR, "system tar not installed")
    def test_list_system_archive_file_and_stdin(self):
        arc = system_archive(self.root, FILES)
        r = run_tool(["-tf", arc], cwd=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.decode().splitlines(),
                         ["file1.txt", "file2.txt", "file3.txt"])
        with open(arc, "rb") as fh:
            data = fh.read()
        r = run_tool(["-t"], cwd=self.root, stdin_data=data)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.decode().splitlines(),
                         ["file1.txt", "file2.txt", "file3.txt"])

    @unittest.skipUnless(HAS_TAR, "system tar not installed")
    def test_verbose_list(self):
        arc = system_archive(self.root, FILES)
        r = run_tool(["-tvf", arc], cwd=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        for name in FILES:
            self.assertIn(name, r.stdout.decode())
        self.assertIn("16", r.stdout.decode())  # "File N contents\n"

    @unittest.skipUnless(HAS_TAR, "system tar not installed")
    def test_extract_system_archive(self):
        arc = system_archive(self.root, FILES)
        out = os.path.join(self.root, "out")
        os.makedirs(out)
        r = run_tool(["-xf", arc], cwd=out)
        self.assertEqual(r.returncode, 0, r.stderr)
        for name, data in FILES.items():
            with open(os.path.join(out, name), "rb") as fh:
                self.assertEqual(fh.read(), data)

    @unittest.skipUnless(HAS_TAR, "system tar not installed")
    def test_create_readable_by_system_tar_and_tarfile(self):
        src = os.path.join(self.root, "src")
        os.makedirs(src)
        write_files(src, FILES)
        arc = os.path.join(self.root, "ours.tar")
        r = run_tool(["-cf", arc] + sorted(FILES), cwd=src)
        self.assertEqual(r.returncode, 0, r.stderr)
        with tarfile.open(arc) as tf:
            self.assertEqual(tf.getnames(),
                             ["file1.txt", "file2.txt", "file3.txt"])
        out = os.path.join(self.root, "out")
        os.makedirs(out)
        subprocess.run(["tar", "-xf", arc], cwd=out, check=True,
                       capture_output=True)
        for name, data in FILES.items():
            with open(os.path.join(out, name), "rb") as fh:
                self.assertEqual(fh.read(), data)

    def test_round_trip_sizes_and_binary(self):
        src = os.path.join(self.root, "src")
        os.makedirs(src)
        mapping = {"empty": b"", "one": b"x", "exact512": b"a" * 512,
                   "over": b"b" * 513, "bin": bytes(range(256)) * 3}
        write_files(src, mapping)
        arc = os.path.join(self.root, "rt.tar")
        r = run_tool(["-cf", arc] + sorted(mapping), cwd=src)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(arc, "rb") as fh:
            raw = fh.read()
        self.assertEqual(len(raw) % 512, 0)
        self.assertTrue(raw.endswith(b"\x00" * 1024))
        r = run_tool(["-tf", arc], cwd=self.root)
        self.assertEqual(r.stdout.decode().splitlines(), sorted(mapping))
        out = os.path.join(self.root, "out")
        os.makedirs(out)
        r = run_tool(["-xf", arc], cwd=out)
        self.assertEqual(r.returncode, 0, r.stderr)
        for name, data in mapping.items():
            with open(os.path.join(out, name), "rb") as fh:
                self.assertEqual(fh.read(), data)

    def test_directories_and_empty_dir(self):
        src = os.path.join(self.root, "src")
        os.makedirs(os.path.join(src, "sub", "deep"))
        os.makedirs(os.path.join(src, "empty"))
        write_files(src, {"sub/a.txt": b"hi\n", "sub/deep/b.txt": b"yo\n"})
        arc = os.path.join(self.root, "dirs.tar")
        r = run_tool(["-cf", arc, "sub", "empty"], cwd=src)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_tool(["-tf", arc], cwd=self.root)
        names = r.stdout.decode().splitlines()
        self.assertIn("sub/", names)
        self.assertIn("empty/", names)
        self.assertIn("sub/deep/b.txt", names)
        out = os.path.join(self.root, "out")
        os.makedirs(out)
        r = run_tool(["-xf", arc], cwd=out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isdir(os.path.join(out, "empty")))
        with open(os.path.join(out, "sub", "deep", "b.txt"), "rb") as fh:
            self.assertEqual(fh.read(), b"yo\n")

    def test_symlink_round_trip(self):
        src = os.path.join(self.root, "src")
        os.makedirs(src)
        write_files(src, {"real.txt": b"target\n"})
        os.symlink("real.txt", os.path.join(src, "link.txt"))
        arc = os.path.join(self.root, "link.tar")
        r = run_tool(["-cf", arc, "real.txt", "link.txt"], cwd=src)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = os.path.join(self.root, "out")
        os.makedirs(out)
        r = run_tool(["-xf", arc], cwd=out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.islink(os.path.join(out, "link.txt")))
        self.assertEqual(os.readlink(os.path.join(out, "link.txt")),
                         "real.txt")

    def test_mode_preserved(self):
        src = os.path.join(self.root, "src")
        os.makedirs(src)
        path = os.path.join(src, "exec.sh")
        with open(path, "wb") as fh:
            fh.write(b"#!/bin/sh\n")
        os.chmod(path, 0o751)
        arc = os.path.join(self.root, "mode.tar")
        r = run_tool(["-cf", arc, "exec.sh"], cwd=src)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = os.path.join(self.root, "out")
        os.makedirs(out)
        r = run_tool(["-xf", arc], cwd=out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(stat.S_IMODE(os.stat(
            os.path.join(out, "exec.sh")).st_mode), 0o751)

    def test_errors(self):
        r = run_tool(["-tf", os.path.join(self.root, "nope.tar")],
                     cwd=self.root)
        self.assertNotEqual(r.returncode, 0)
        # Corrupt checksum.
        raw = bytearray(build_header("x.txt", 0o644, 0, 0, 3, 0, "0"))
        raw[5] ^= 0x01  # corrupt the stored name -> checksum mismatch
        raw += b"abc" + b"\x00" * 509 + b"\x00" * 1024
        bad = os.path.join(self.root, "bad.tar")
        with open(bad, "wb") as fh:
            fh.write(bytes(raw))
        r = run_tool(["-tf", bad], cwd=self.root)
        self.assertNotEqual(r.returncode, 0)
        # Truncated archive.
        trunc = os.path.join(self.root, "trunc.tar")
        with open(trunc, "wb") as fh:
            fh.write(build_header("x.txt", 0o644, 0, 0, 10, 0, "0")[:100])
        r = run_tool(["-tf", trunc], cwd=self.root)
        self.assertNotEqual(r.returncode, 0)
        # Missing create input.
        r = run_tool(["-cf", os.path.join(self.root, "o.tar"), "gone.txt"],
                     cwd=self.root)
        self.assertNotEqual(r.returncode, 0)

    def test_traversal_refused(self):
        arc = os.path.join(self.root, "evil.tar")
        entry = build_header("../evil.txt", 0o644, 0, 0, 3, 0, "0")
        with open(arc, "wb") as fh:
            fh.write(entry + b"evil" + b"\x00" * 508 + b"\x00" * 1024)
        out = os.path.join(self.root, "out")
        os.makedirs(out)
        r = run_tool(["-xf", arc], cwd=out)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.root, "evil.txt")))

    def test_iter_entries_oracle_free(self):
        # In-process check that iter_entries skips data correctly.
        buf = io.BytesIO()
        buf.write(build_header("a.txt", 0o644, 0, 0, 5, 0, "0"))
        buf.write(b"hello" + b"\x00" * 507)
        buf.write(build_header("b.txt", 0o644, 0, 0, 0, 0, "0"))
        buf.write(b"\x00" * 1024)
        buf.seek(0)
        got = [(h.name, d) for h, d in iter_entries(buf)]
        self.assertEqual(got, [("a.txt", b"hello"), ("b.txt", b"")])


if __name__ == "__main__":
    unittest.main()
