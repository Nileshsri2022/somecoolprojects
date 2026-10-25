"""Tests for huffman.py. Run from compression/:
python3 -m unittest discover -s tests -v

Function tests (roundtrip, code properties) and CLI subprocess
tests (files, corrupt inputs).
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from huffman import (HuffmanError, build_codes, build_tree,  # noqa: E402
                     compress, decompress, frequencies)

TOOL = os.path.join(os.path.dirname(__file__), "..", "huffman.py")
PARAGRAPH = (b"The quick brown fox jumps over the lazy dog. "
             b"Pack my box with five dozen liquor jugs. ")


def is_prefix_free(codes):
    code_list = list(codes.values())
    for i, a in enumerate(code_list):
        for j, b in enumerate(code_list):
            if i != j and b.startswith(a):
                return False
    return True


def run_cli(args):
    proc = subprocess.run(
        [sys.executable, TOOL, *args],
        capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


class TestFunctions(unittest.TestCase):
    def test_frequencies(self):
        self.assertEqual(frequencies(b"aaabbc"), {97: 3, 98: 2, 99: 1})

    def test_empty(self):
        self.assertEqual(compress(b""), b"CHUF\x00\x00\x00\x00")
        self.assertEqual(decompress(compress(b"")), b"")

    def test_single_byte_and_single_symbol(self):
        for data in (b"a", b"aaaaaaa"):
            with self.subTest(data=data):
                self.assertEqual(decompress(compress(data)), data)

    def test_challenge_example_codes(self):
        codes = build_codes(build_tree(frequencies(b"aaabbc")))
        self.assertTrue(is_prefix_free(codes))
        # Most frequent symbol must have the shortest code.
        self.assertLessEqual(len(codes[97]), len(codes[98]))
        self.assertLessEqual(len(codes[97]), len(codes[99]))
        self.assertEqual(decompress(compress(b"aaabbc")), b"aaabbc")

    def test_all_byte_values(self):
        data = bytes(range(256)) * 2
        self.assertEqual(decompress(compress(data)), data)

    def test_repetitive_smaller(self):
        data = PARAGRAPH * 200
        compressed = compress(data)
        self.assertEqual(decompress(compressed), data)
        self.assertLess(len(compressed), len(data))

    def test_larger_repetitive(self):
        data = (b"hello world, hello Huffman, hello again. " * 3000)
        compressed = compress(data)
        self.assertEqual(decompress(compressed), data)
        self.assertLess(len(compressed), len(data))
        print(f"\n  larger case: {len(data)} -> {len(compressed)} "
              f"({100 * len(compressed) // len(data)}%)")

    def test_corrupt(self):
        with self.assertRaises(HuffmanError):
            decompress(b"XXXX\x00\x00\x00\x00")
        with self.assertRaises(HuffmanError):
            decompress(b"CHUF\x00\x00\x00\x01")  # header truncated
        good = compress(b"hello world, hello Huffman")
        with self.assertRaises(HuffmanError):
            decompress(good[:-1])  # bitstream truncated


class TestCli(unittest.TestCase):
    def test_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.txt")
            comp = os.path.join(tmp, "in.huff")
            dst = os.path.join(tmp, "out.txt")
            data = PARAGRAPH * 100
            with open(src, "wb") as f:
                f.write(data)
            code, _, _ = run_cli(["compress", src, comp])
            self.assertEqual(code, 0)
            self.assertLess(os.path.getsize(comp), len(data))
            code, _, _ = run_cli(["decompress", comp, dst])
            self.assertEqual(code, 0)
            with open(dst, "rb") as f:
                self.assertEqual(f.read(), data)

    def test_cli_errors(self):
        code, _, err = run_cli(["compress"])
        self.assertNotEqual(code, 0)
        code, _, err = run_cli(["bogus", "a", "b"])
        self.assertNotEqual(code, 0)
        code, _, err = run_cli(["compress", "/nonexistent-xyz", "o"])
        self.assertNotEqual(code, 0)
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.huff")
            with open(bad, "wb") as f:
                f.write(b"XXXX\x00\x00\x00\x00")
            code, _, err = run_cli(["decompress", bad,
                                    os.path.join(tmp, "out")])
            self.assertNotEqual(code, 0)
            self.assertIn("bad magic", err)


if __name__ == "__main__":
    unittest.main()
