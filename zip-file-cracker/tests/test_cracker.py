"""Tests for zip-file-cracker. Synthetic fixtures only.

Every encrypted zip is created inside the test run by
_write_encrypted_zip (stored method, traditional ZipCrypto,
the inverse of zipfile._ZipDecrypter). No real protected
archive, no real credential, no downloaded wordlist.
"""
import io
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cracker

CRCTABLE = [zipfile._gen_crc(i) for i in range(256)]


def _crc_byte(ch, crc):
    return (crc >> 8) ^ CRCTABLE[(crc ^ ch) & 0xFF]


class _Encrypter:
    """ZipCrypto encryptor (inverse of zipfile._ZipDecrypter)."""

    def __init__(self, pwd):
        self.k0, self.k1, self.k2 = 0x12345678, 0x23456789, 0x34567890
        for p in pwd:
            self._update(p)

    def _update(self, c):
        self.k0 = _crc_byte(c, self.k0)
        self.k1 = (self.k1 + (self.k0 & 0xFF)) & 0xFFFFFFFF
        self.k1 = (self.k1 * 134775813 + 1) & 0xFFFFFFFF
        self.k2 = _crc_byte(self.k1 >> 24, self.k2)

    def encrypt(self, data):
        out = bytearray()
        for c in data:
            k = self.k2 | 2
            out.append(c ^ ((k * (k ^ 1)) >> 8) & 0xFF)
            self._update(c)
        return bytes(out)


def _write_encrypted_zip(path, name, data, password):
    """Write a minimal stored ZipCrypto zip (test fixture only)."""
    crc = zlib.crc32(data) & 0xFFFFFFFF
    enc = _Encrypter(password.encode("utf-8"))
    header = bytes([0x11] * 11) + bytes([(crc >> 24) & 0xFF])
    enc_data = enc.encrypt(header + data)
    name_b = name.encode()
    local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0x0001, 0, 0, 0,
                        crc, len(enc_data), len(data), len(name_b), 0) + name_b
    central = struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0x0001,
                          0, 0, 0, crc, len(enc_data), len(data), len(name_b),
                          0, 0, 0, 0, 0, 0) + name_b
    eocd = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1,
                       len(central), len(local) + len(enc_data), 0)
    with open(path, "wb") as f:
        f.write(local)
        f.write(enc_data)
        f.write(central)
        f.write(eocd)


def _patch_central_method_to_aes(path):
    """Turn a fixture's central-directory method into 99 (AES marker)."""
    with open(path, "r+b") as f:
        data = bytearray(f.read())
        idx = data.find(b"PK\x01\x02")
        assert idx >= 0
        data[idx + 10:idx + 12] = struct.pack("<H", 99)
        f.seek(0)
        f.write(data)


class ZipCrackerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.zip_path = os.path.join(self.dir, "cctest.zip")
        _write_encrypted_zip(self.zip_path, "cc.txt",
                             b"synthetic content", "test")
        self.words = os.path.join(self.dir, "words.txt")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_words(self, text):
        with open(self.words, "w") as f:
            f.write(text)

    def _run_cli(self, *args):
        return subprocess.run(
            [sys.executable, cracker.__file__] + list(args),
            capture_output=True, text=True, cwd=self.dir)

    # --- fixture sanity (must pass before attack tests mean anything) ---
    def test_fixture_round_trips_with_stdlib(self):
        with zipfile.ZipFile(self.zip_path) as zf:
            self.assertEqual(zf.read("cc.txt", pwd=b"test"),
                             b"synthetic content")
            self.assertTrue(zf.infolist()[0].flag_bits & 0x1)
        with self.assertRaises(RuntimeError):
            with zipfile.ZipFile(self.zip_path) as zf:
                zf.read("cc.txt", pwd=b"wrong")

    # --- Step 1: headers ---
    def test_has_zip_headers(self):
        self.assertTrue(cracker.has_zip_headers(self.zip_path))
        plain = os.path.join(self.dir, "cc.txt")
        with open(plain, "w") as f:
            f.write("not a zip")
        self.assertFalse(cracker.has_zip_headers(plain))
        empty = os.path.join(self.dir, "empty.bin")
        open(empty, "wb").close()
        self.assertFalse(cracker.has_zip_headers(empty))
        self.assertFalse(cracker.has_zip_headers(os.path.join(self.dir, "nope.zip")))

    def test_cli_header_mode(self):
        out = self._run_cli(self.zip_path)
        self.assertEqual(out.stdout.strip(), "Has zip headers.")
        self.assertEqual(out.returncode, 0)
        plain = os.path.join(self.dir, "cc.txt")
        with open(plain, "w") as f:
            f.write("not a zip")
        out = self._run_cli(plain)
        self.assertEqual(out.stdout.strip(), "Does not have zip headers.")
        self.assertEqual(out.returncode, 1)

    # --- Step 2: dictionary ---
    def test_dictionary_finds_password_with_exact_attempts(self):
        self._write_words("alpha\nbeta\ntest\ngamma\n")
        found, attempts = cracker.dictionary_attack(self.zip_path, self.words)
        self.assertEqual(found, "test")
        self.assertEqual(attempts, 3)

    def test_dictionary_not_found(self):
        self._write_words("alpha\nbeta\n")
        found, attempts = cracker.dictionary_attack(self.zip_path, self.words)
        self.assertIsNone(found)
        self.assertEqual(attempts, 2)

    def test_dictionary_skips_blank_lines(self):
        self._write_words("\n\ntest\n")
        found, attempts = cracker.dictionary_attack(self.zip_path, self.words)
        self.assertEqual(found, "test")
        self.assertEqual(attempts, 1)

    def test_dictionary_missing_wordlist(self):
        with self.assertRaises(FileNotFoundError):
            cracker.dictionary_attack(self.zip_path,
                                      os.path.join(self.dir, "missing.txt"))

    def test_cli_dict(self):
        self._write_words("alpha\ntest\n")
        out = self._run_cli("-dict", self.zip_path, "--wordlist", self.words)
        self.assertIn("Password found: test", out.stdout)
        self.assertEqual(out.returncode, 0)

    def test_cli_dict_without_wordlist_exits_2(self):
        out = self._run_cli("-dict", self.zip_path)
        self.assertEqual(out.returncode, 2)

    def test_cli_dict_not_found(self):
        self._write_words("alpha\n")
        out = self._run_cli("-dict", self.zip_path, "--wordlist", self.words,
                            "--workers", "1")
        self.assertIn("Password not found.", out.stdout)
        self.assertEqual(out.returncode, 1)

    # --- Step 3: brute force ---
    def test_brute_finds_ab(self):
        path = os.path.join(self.dir, "ab.zip")
        _write_encrypted_zip(path, "cc.txt", b"x", "ab")
        found, attempts = cracker.brute_force_attack(
            path, charset="ab", min_length=1, max_length=2)
        self.assertEqual(found, "ab")
        self.assertEqual(attempts, 4)  # a, b, aa, ab

    def test_brute_finds_test_with_restricted_charset(self):
        # charset "test" de-duplicates to t, e, s; "test" is the
        # 16th length-4 candidate after 3+9+27 shorter ones = 55.
        found, attempts = cracker.brute_force_attack(
            self.zip_path, charset="test", min_length=1, max_length=4)
        self.assertEqual(found, "test")
        self.assertEqual(attempts, 55)

    def test_brute_not_found_in_bounded_space(self):
        found, attempts = cracker.brute_force_attack(
            self.zip_path, charset="ab", min_length=1, max_length=2)
        self.assertIsNone(found)
        self.assertEqual(attempts, 2 + 4)

    def test_brute_validation(self):
        with self.assertRaises(ValueError):
            cracker.brute_force_attack(self.zip_path, charset="")
        with self.assertRaises(ValueError):
            cracker.brute_force_attack(self.zip_path, min_length=0)
        with self.assertRaises(ValueError):
            cracker.brute_force_attack(self.zip_path, min_length=3, max_length=2)

    def test_max_attempts_stops_search(self):
        found, attempts = cracker.brute_force_attack(
            self.zip_path, charset="ab", min_length=1, max_length=3,
            max_attempts=2)
        self.assertIsNone(found)
        self.assertEqual(attempts, 2)

    def test_cli_brute_page_example(self):
        out = self._run_cli("-brute", "-min=1", "-max=4", self.zip_path,
                            "--charset", "test", "--workers", "1")
        self.assertIn("Password found: test", out.stdout)
        self.assertEqual(out.returncode, 0)

    # --- Step 4: concurrency ---
    def test_parallel_dictionary_still_finds(self):
        self._write_words("alpha\nbeta\ntest\ngamma\n")
        found, attempts = cracker.dictionary_attack(
            self.zip_path, self.words, workers=4)
        self.assertEqual(found, "test")
        self.assertGreaterEqual(attempts, 3)

    def test_default_workers_is_cpu_count(self):
        self.assertEqual(cracker._default_workers(), os.cpu_count() or 1)

    # --- guards / divergences ---
    def test_try_password(self):
        self.assertTrue(cracker.try_password(self.zip_path, "test"))
        self.assertFalse(cracker.try_password(self.zip_path, "wrong"))

    def test_unencrypted_zip_never_matches(self):
        plain_zip = os.path.join(self.dir, "plain.zip")
        with zipfile.ZipFile(plain_zip, "w") as zf:
            zf.writestr("cc.txt", "plain content")
        self.assertFalse(cracker.try_password(plain_zip, "anything"))
        self._write_words("anything\n")
        found, _ = cracker.dictionary_attack(plain_zip, self.words)
        self.assertIsNone(found)

    def test_empty_archive_raises(self):
        empty_zip = os.path.join(self.dir, "empty.zip")
        with zipfile.ZipFile(empty_zip, "w"):
            pass
        with self.assertRaises(ValueError):
            cracker.dictionary_attack(empty_zip, self.words)

    def test_unknown_member_raises(self):
        with self.assertRaises(ValueError):
            cracker.dictionary_attack(self.zip_path, self.words,
                                      member="nope.txt")

    def test_aes_marker_raises(self):
        aes_zip = os.path.join(self.dir, "aes.zip")
        _write_encrypted_zip(aes_zip, "cc.txt", b"x", "test")
        _patch_central_method_to_aes(aes_zip)
        with self.assertRaises(cracker.UnsupportedEncryptionError):
            cracker.dictionary_attack(aes_zip, self.words)

    def test_nested_zip_detection(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as zf:
            zf.writestr("inner.txt", "inner")
        outer = os.path.join(self.dir, "outer.zip")
        _write_encrypted_zip(outer, "inner.zip", inner.getvalue(), "test")
        data = cracker.read_decrypted(outer, "test")
        self.assertTrue(cracker.looks_like_zip(data))
        self.assertFalse(cracker.looks_like_zip(b"plain content"))
        self._write_words("test\n")
        out = self._run_cli("-dict", outer, "--wordlist", self.words,
                            "--workers", "1")
        self.assertIn("Password found: test", out.stdout)
        self.assertIn("nested zip", out.stdout)


if __name__ == "__main__":
    unittest.main()
