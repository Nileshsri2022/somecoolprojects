"""Tests for spell_checker.py — small synthetic dictionaries only."""

import os
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spell_checker import (  # noqa: E402
    BloomFilter,
    _fnv1a_64,
    build_filter,
    check_words,
    load_dictionary,
    load_filter,
    optimal_parameters,
    save_filter,
)

DICT_WORDS = [
    "hi", "hello", "word", "concurrency", "up", "apple", "banana",
    "cherry", "dog", "elephant", "frog", "grape", "house", "igloo",
    "jungle", "kite", "lemon", "monkey", "night", "ocean", "piano",
    "queen", "river", "sun", "tiger", "umbrella", "violet", "whale",
    "xylophone", "yellow", "zebra", "bread", "cloud", "dance", "eagle",
    "flute", "garden", "hammer", "island", "jacket", "koala", "lion",
    "mountain", "notebook", "orange", "penguin", "quilt", "rocket",
    "sailor", "tomato",
]


class TestSizing(unittest.TestCase):
    def test_known_values(self):
        bits, hashes = optimal_parameters(1000, 0.01)
        self.assertEqual(bits, 9586)
        self.assertEqual(hashes, 7)

    def test_grows_with_n_and_stricter_rate(self):
        small, _ = optimal_parameters(100, 0.01)
        big, _ = optimal_parameters(1000, 0.01)
        stricter, _ = optimal_parameters(1000, 0.001)
        self.assertLess(small, big)
        self.assertLess(big, stricter)

    def test_hashes_at_least_one(self):
        _, hashes = optimal_parameters(1, 0.5)
        self.assertGreaterEqual(hashes, 1)

    def test_invalid_inputs(self):
        for n, p in [(0, 0.01), (-5, 0.01), (10, 0), (10, 1), (10, 1.5)]:
            with self.assertRaises(ValueError):
                optimal_parameters(n, p)

    def test_theoretical_rate_meets_target(self):
        for n, p in [(100, 0.01), (1000, 0.01), (500, 0.001)]:
            bits, hashes = optimal_parameters(n, p)
            filt = BloomFilter(bits, hashes)
            self.assertLessEqual(filt.estimated_false_positive_rate(n), p * 1.05)


class TestHashing(unittest.TestCase):
    def test_fnv1a_vectors(self):
        self.assertEqual(_fnv1a_64(""), 0xCBF29CE484222325)
        self.assertEqual(_fnv1a_64("a"), 0xAF63DC4C8601EC8C)

    def test_positions_in_range(self):
        filt = BloomFilter(101, 4)
        for word in DICT_WORDS:
            for pos in filt._positions(word):
                self.assertGreaterEqual(pos, 0)
                self.assertLess(pos, 101)


class TestMembership(unittest.TestCase):
    def test_no_false_negatives(self):
        filt = build_filter(DICT_WORDS)
        for word in DICT_WORDS:
            self.assertIn(word, filt, f"false negative: {word}")

    def test_add_idempotent(self):
        filt = build_filter(DICT_WORDS)
        before = filt.to_bytes()
        for word in DICT_WORDS:
            filt.add(word)
        self.assertEqual(before, filt.to_bytes())

    def test_case_insensitive(self):
        filt = build_filter(["hello"])
        self.assertIn("Hello", filt)
        self.assertIn("HELLO", filt)

    def test_empty_word(self):
        filt = build_filter(["hello"])
        self.assertNotIn("", filt)
        with self.assertRaises(ValueError):
            filt.add("")

    def test_absent_word_usually_absent(self):
        # A large filter vs a small dictionary: most held-out words
        # must be absent; exact verdicts are hash-determined, so we
        # only assert the bulk, not any single word.
        filt = build_filter(DICT_WORDS, fp_rate=0.001)
        held_out = [f"heldout{i}" for i in range(200)]
        absent = sum(1 for w in held_out if w not in filt)
        self.assertGreaterEqual(absent, 190)


class TestFalsePositives(unittest.TestCase):
    def test_measured_rate_bounded(self):
        filt = build_filter(DICT_WORDS, fp_rate=0.01)
        held_out = [f"heldout{i:04d}" for i in range(1000)]
        rate = sum(1 for w in held_out if w in filt) / len(held_out)
        self.assertLess(rate, 0.10,
                        f"measured false-positive rate {rate:.3f} too high")

    def test_saturated_tiny_filter_has_false_positives(self):
        filt = BloomFilter(16, 2)
        for word in DICT_WORDS:
            filt.add(word)
        held_out = [f"heldout{i:04d}" for i in range(200)]
        rate = sum(1 for w in held_out if w in filt) / len(held_out)
        self.assertGreater(rate, 0, "saturated filter showed no false positives")


class TestFileFormat(unittest.TestCase):
    def test_header_and_roundtrip(self):
        filt = build_filter(DICT_WORDS)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "words.bf")
            save_filter(filt, path)
            with open(path, "rb") as f:
                data = f.read()
            self.assertEqual(data[:4], b"CCBF")
            version, hashes, bits = struct.unpack(">HHI", data[4:12])
            self.assertEqual(version, 1)
            self.assertEqual(hashes, filt.num_hashes)
            self.assertEqual(bits, filt.num_bits)
            self.assertEqual(len(data), 12 + (bits + 7) // 8)
            loaded = load_filter(path)
            self.assertEqual(loaded.num_bits, filt.num_bits)
            self.assertEqual(loaded.num_hashes, filt.num_hashes)
            for word in DICT_WORDS:
                self.assertIn(word, loaded)
            self.assertEqual(check_words(filt, ["zzzqqq", "hello"]),
                             check_words(loaded, ["zzzqqq", "hello"]))

    def test_corrupt_files_rejected(self):
        filt = build_filter(DICT_WORDS)
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "words.bf")
            save_filter(filt, good)
            with open(good, "rb") as f:
                data = f.read()

            def expect_error(blob, name):
                path = os.path.join(tmp, name)
                with open(path, "wb") as f:
                    f.write(blob)
                with self.assertRaises(ValueError):
                    load_filter(path)

            expect_error(b"XXXX" + data[4:], "bad_magic.bf")
            expect_error(data[:4] + struct.pack(">H", 2) + data[6:],
                         "bad_version.bf")
            expect_error(data[:4] + data[4:6] + struct.pack(">H", 0) + data[8:],
                         "zero_hashes.bf")
            expect_error(data[:4] + data[4:6] + data[6:8] + struct.pack(">I", 0)
                         + data[12:], "zero_bits.bf")
            expect_error(data[:-1], "truncated.bf")
            expect_error(data + b"\x00", "trailing.bf")
            expect_error(b"short", "short.bf")


class TestDictionaryLoading(unittest.TestCase):
    def test_normalisation_and_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "dict.txt")
            with open(path, "w") as f:
                f.write("Hello\n\nHELLO\nworld\n  World  \n")
            self.assertEqual(load_dictionary(path), ["hello", "world"])


class TestCLI(unittest.TestCase):
    def run_cli(self, args, cwd):
        return subprocess.run(
            [sys.executable, "spell_checker.py"] + args,
            cwd=cwd, capture_output=True, text=True, timeout=30)

    def test_build_and_check_page_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            dict_path = os.path.join(tmp, "dict.txt")
            with open(dict_path, "w") as f:
                f.write("\n".join(DICT_WORDS) + "\n")
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # Copy the script into tmp so the run is self-contained.
            import shutil
            shutil.copy(os.path.join(here, "spell_checker.py"),
                        os.path.join(tmp, "spell_checker.py"))
            built = self.run_cli(["-build", "dict.txt"], tmp)
            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertIn("words", built.stdout)
            self.assertTrue(os.path.exists(os.path.join(tmp, "words.bf")))
            checked = self.run_cli(
                ["words.bf", "hi", "hello", "word", "concurrency",
                 "coding", "challenges", "imadethis", "up"], tmp)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertEqual(
                checked.stdout,
                "These words are spelt wrong:\n"
                " coding\n challenges\n imadethis\n")
            all_ok = self.run_cli(["words.bf", "hi", "hello", "up"], tmp)
            self.assertEqual(all_ok.returncode, 0)
            self.assertEqual(all_ok.stdout, "")

    def test_bad_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            import shutil
            shutil.copy(os.path.join(here, "spell_checker.py"),
                        os.path.join(tmp, "spell_checker.py"))
            self.assertNotEqual(self.run_cli([], tmp).returncode, 0)
            self.assertNotEqual(
                self.run_cli(["-build", "missing.txt"], tmp).returncode, 0)
            self.assertNotEqual(
                self.run_cli(["missing.bf", "hello"], tmp).returncode, 0)


if __name__ == "__main__":
    unittest.main()
