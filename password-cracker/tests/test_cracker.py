"""Tests for cracker.py — all targets are hashes of synthetic
passwords generated inside the test run. No real passwords,
no leaked lists, no downloaded wordlists, no page examples."""

import hashlib
import io
import itertools
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cracker
from cracker import (
    brute_force_attack,
    build_rainbow_table,
    crack,
    dictionary_attack,
    hash_password,
    load_rainbow_table,
    main,
    md5_hex,
    read_wordlist,
    write_rainbow_table,
)


def synth_hash(password, algo="md5"):
    return hashlib.new(algo, password.encode()).hexdigest()


class TestMD5(unittest.TestCase):
    def test_matches_hashlib(self):
        cases = [
            b"",
            b"a",
            b"abc",
            b"message digest",
            b"x" * 55,   # padding boundary: fits with length in one block
            b"x" * 56,   # padding spills into a second block
            b"x" * 63,
            b"x" * 64,
            b"x" * 65,
            b"x" * 1000,
            "pässwörd".encode("utf-8"),
        ]
        for data in cases:
            with self.subTest(data=data[:20]):
                self.assertEqual(md5_hex(data), hashlib.md5(data).hexdigest())

    def test_format(self):
        digest = md5_hex(b"abc")
        self.assertEqual(len(digest), 32)
        self.assertEqual(digest, digest.lower())
        int(digest, 16)  # valid hex


class TestHashPassword(unittest.TestCase):
    def test_all_algos_match_hashlib(self):
        for algo in ("md5", "sha1", "sha256", "sha512"):
            self.assertEqual(
                hash_password("apple", algo), synth_hash("apple", algo))

    def test_salt_positions(self):
        plain = hash_password("apple")
        prefix = hash_password("apple", salt="pep", salt_position="prefix")
        suffix = hash_password("apple", salt="pep", salt_position="suffix")
        self.assertEqual(prefix, synth_hash("pepapple"))
        self.assertEqual(suffix, synth_hash("applepep"))
        self.assertNotEqual(prefix, plain)
        self.assertNotEqual(suffix, plain)
        self.assertNotEqual(prefix, suffix)
        self.assertEqual(
            hash_password("apple", salt="pep", salt_position="none"), plain)
        # Reproducible.
        self.assertEqual(prefix, hash_password("apple", salt="pep"))

    def test_errors(self):
        with self.assertRaises(ValueError):
            hash_password("apple", algo="md6")
        with self.assertRaises(ValueError):
            hash_password("apple", salt_position="middle")


class TestDictionary(unittest.TestCase):
    def test_found_with_attempt_count(self):
        words = ["alpha", "beta", "gamma", "delta"]
        found, attempts = dictionary_attack(synth_hash("gamma"), words)
        self.assertEqual(found, "gamma")
        self.assertEqual(attempts, 3)

    def test_not_found(self):
        found, attempts = dictionary_attack(
            synth_hash("missing"), ["alpha", "beta"])
        self.assertIsNone(found)
        self.assertEqual(attempts, 2)

    def test_sha256_and_salted(self):
        words = ["one", "two"]
        found, _ = dictionary_attack(synth_hash("two", "sha256"), words, algo="sha256")
        self.assertEqual(found, "two")
        salted = hash_password("two", salt="s", salt_position="suffix")
        found, _ = dictionary_attack(salted, words, salt="s", salt_position="suffix")
        self.assertEqual(found, "two")
        # Wrong salt must not match.
        found, _ = dictionary_attack(salted, words, salt="other")
        self.assertIsNone(found)

    def test_wordlist_file_skips_blank_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "words.txt")
            with open(path, "w") as fh:
                fh.write("alpha\n\nbeta\n")
            self.assertEqual(list(read_wordlist(path)), ["alpha", "beta"])
            found, attempts = dictionary_attack(
                synth_hash("beta"), read_wordlist(path))
            self.assertEqual((found, attempts), ("beta", 2))

    def test_max_attempts(self):
        found, attempts = dictionary_attack(
            synth_hash("gamma"), ["alpha", "beta", "gamma"], max_attempts=2)
        self.assertIsNone(found)
        self.assertEqual(attempts, 2)


class TestBruteForce(unittest.TestCase):
    def test_found_with_exact_attempt_count(self):
        # Order: a, b, aa, ab, ba, bb -> "ba" is attempt 5.
        found, attempts = brute_force_attack(
            synth_hash("ba"), "ab", 1, 2)
        self.assertEqual((found, attempts), ("ba", 5))

    def test_single_char(self):
        found, attempts = brute_force_attack(synth_hash("c"), "abc", 1, 1)
        self.assertEqual((found, attempts), ("c", 3))

    def test_min_length_respected(self):
        # "a" exists but is below min_length=2.
        found, attempts = brute_force_attack(synth_hash("a"), "ab", 2, 2)
        self.assertIsNone(found)
        self.assertEqual(attempts, 4)

    def test_not_found_counts_all(self):
        found, attempts = brute_force_attack(synth_hash("zz"), "ab", 1, 2)
        self.assertIsNone(found)
        self.assertEqual(attempts, 2 + 4)

    def test_max_attempts(self):
        found, attempts = brute_force_attack(
            synth_hash("bb"), "ab", 1, 2, max_attempts=3)
        self.assertIsNone(found)
        self.assertEqual(attempts, 3)

    def test_errors(self):
        target = synth_hash("a")
        with self.assertRaises(ValueError):
            brute_force_attack(target, "", 1, 2)
        with self.assertRaises(ValueError):
            brute_force_attack(target, "ab", 0, 2)
        with self.assertRaises(ValueError):
            brute_force_attack(target, "ab", 3, 2)


class TestRainbowTable(unittest.TestCase):
    def test_build_and_roundtrip(self):
        table = build_rainbow_table(["apple", "pear", "plum"])
        self.assertEqual(table[synth_hash("pear")], "pear")
        self.assertEqual(len(table), 3)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "table.txt")
            write_rainbow_table(path, table)
            loaded = load_rainbow_table(path)
            self.assertEqual(loaded, table)

    def test_first_wins_on_duplicate_hash(self):
        # Duplicate password entries collapse to the first via setdefault.
        table = build_rainbow_table(["apple", "apple"])
        self.assertEqual(len(table), 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "table.txt")
            with open(path, "w") as fh:
                fh.write(f"{synth_hash('apple')}\tfirst\n")
                fh.write(f"{synth_hash('apple')}\tsecond\n")
                fh.write("malformed-line-no-tab\n")
                fh.write("\tno-hash\n")
            loaded = load_rainbow_table(path)
            self.assertEqual(loaded, {synth_hash("apple"): "first"})

    def test_crack_via_table(self):
        table = build_rainbow_table(["apple", "pear"])
        found, _ = crack(synth_hash("pear"), "rainbow", table=table)
        self.assertEqual(found, "pear")
        found, _ = crack(synth_hash("missing"), "rainbow", table=table)
        self.assertIsNone(found)

    def test_brute_candidates_to_table_end_to_end(self):
        # Step 4 -> 5: generate candidates, build table, crack from it.
        candidates = ["".join(c) for length in (1, 2)
                      for c in itertools.product("ab", repeat=length)]
        table = build_rainbow_table(candidates)
        found, _ = crack(synth_hash("ab"), "rainbow", table=table)
        self.assertEqual(found, "ab")

    def test_crack_errors(self):
        with self.assertRaises(ValueError):
            crack(synth_hash("a"), "dict")
        with self.assertRaises(ValueError):
            crack(synth_hash("a"), "brute")
        with self.assertRaises(ValueError):
            crack(synth_hash("a"), "rainbow")
        with self.assertRaises(ValueError):
            crack(synth_hash("a"), "sideways")


class TestCLI(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = main(argv)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_hash_brute_found_and_missed(self):
        code, out, _ = self.run_main([
            "hash", synth_hash("ab"), "--mode", "brute",
            "--charset", "ab", "--min-length", "1", "--max-length", "2"])
        self.assertEqual(code, 0)
        self.assertIn("Password found: ab", out)
        code, out, _ = self.run_main([
            "hash", synth_hash("zz"), "--mode", "brute",
            "--charset", "ab", "--min-length", "1", "--max-length", "2"])
        self.assertEqual(code, 1)
        self.assertIn("Password not found", out)

    def test_hash_dict_and_table_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            words = os.path.join(tmp, "words.txt")
            with open(words, "w") as fh:
                fh.write("alpha\nbeta\ngamma\n")
            code, out, _ = self.run_main([
                "hash", synth_hash("beta"), "--mode", "dict",
                "--wordlist", words])
            self.assertEqual(code, 0)
            self.assertIn("Password found: beta", out)

            table = os.path.join(tmp, "table.txt")
            code, out, _ = self.run_main([
                "build-table", "--wordlist", words, "--output", table])
            self.assertEqual(code, 0)
            self.assertIn("3 entries", out)
            code, out, _ = self.run_main([
                "lookup", synth_hash("gamma"), "--table", table])
            self.assertEqual(code, 0)
            self.assertIn("Password found: gamma", out)
            code, out, _ = self.run_main([
                "lookup", synth_hash("missing"), "--table", table])
            self.assertEqual(code, 1)
            self.assertIn("Password not found", out)

    def test_bad_algorithm_exits_nonzero(self):
        # argparse choices reject it (exit code 2 via SystemExit).
        code, _, err = self.run_main(["hash", "x", "--algo", "md6"])
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", err)


if __name__ == "__main__":
    unittest.main()
