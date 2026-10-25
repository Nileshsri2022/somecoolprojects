"""Tests for password-manager. Synthetic entries only, temp dirs only."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manager import (  # noqa: E402
    CorruptVaultError,
    Vault,
    VaultError,
    WrongPasswordError,
    validate_vault_name,
    vault_path,
)

MASTER = "synthetic-master-password"
RECORD = "cc test record"
USER = "john"
PASSWORD = "secretpassword"
MANAGER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manager.py"
)


def make_vault(tmp, name="cctest", password=MASTER):
    path = vault_path(tmp, name)
    vault = Vault.create(path, password)
    return path, vault


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_create_open_round_trip(self):
        path, vault = make_vault(self.dir)
        vault.add(RECORD, USER, PASSWORD)
        reopened = Vault.open(path, MASTER)
        self.assertEqual(reopened.get(RECORD), (USER, PASSWORD))

    def test_wrong_password_rejected(self):
        path, _ = make_vault(self.dir)
        with self.assertRaises(WrongPasswordError):
            Vault.open(path, "wrong-master-password")

    def test_empty_master_password_rejected(self):
        with self.assertRaises(ValueError):
            Vault.create(vault_path(self.dir, "empty"), "")

    def test_duplicate_add_overwrites(self):
        _, vault = make_vault(self.dir)
        vault.add(RECORD, USER, PASSWORD)
        vault.add(RECORD, "jane", "newpassword")
        self.assertEqual(vault.get(RECORD), ("jane", "newpassword"))
        self.assertEqual(vault.list_names(), [RECORD])

    def test_missing_record(self):
        _, vault = make_vault(self.dir)
        vault.add(RECORD, USER, PASSWORD)
        self.assertIsNone(vault.get("no such record"))
        self.assertFalse(vault.delete("no such record"))
        self.assertEqual(vault.list_names(), [RECORD])

    def test_list_sorted(self):
        _, vault = make_vault(self.dir)
        for name in ("zeta", "alpha", "mid"):
            vault.add(name, "u", "p")
        self.assertEqual(vault.list_names(), ["alpha", "mid", "zeta"])

    def test_delete_persists(self):
        path, vault = make_vault(self.dir)
        vault.add("keep", "u", "p")
        vault.add("drop", "u", "p")
        self.assertTrue(vault.delete("drop"))
        reopened = Vault.open(path, MASTER)
        self.assertIsNone(reopened.get("drop"))
        self.assertIsNotNone(reopened.get("keep"))

    def test_create_existing_fails_without_clobber(self):
        path, vault = make_vault(self.dir)
        vault.add(RECORD, USER, PASSWORD)
        with self.assertRaises(FileExistsError):
            Vault.create(path, "other-master")
        self.assertEqual(Vault.open(path, MASTER).get(RECORD), (USER, PASSWORD))

    def test_open_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            Vault.open(vault_path(self.dir, "ghost"), MASTER)

    def test_unsafe_vault_names(self):
        for bad in ("", ".", "..", "a/b", "a\\b"):
            with self.assertRaises(ValueError, msg=bad):
                validate_vault_name(bad)

    def test_no_plaintext_on_disk(self):
        path, vault = make_vault(self.dir)
        vault.add(RECORD, USER, PASSWORD)
        with open(path, "rb") as fh:
            blob = fh.read()
        self.assertNotIn(PASSWORD.encode(), blob)
        self.assertNotIn(USER.encode(), blob)

    def test_tampered_ciphertext_rejected(self):
        path, vault = make_vault(self.dir)
        vault.add(RECORD, USER, PASSWORD)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["ciphertext"] = ("A" if data["ciphertext"][0] != "A" else "B") + (
            data["ciphertext"][1:]
        )
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        with self.assertRaises(VaultError):
            Vault.open(path, MASTER)

    def test_tampered_tag_rejected(self):
        path, vault = make_vault(self.dir)
        vault.add(RECORD, USER, PASSWORD)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["tag"] = ("A" if data["tag"][0] != "A" else "B") + data["tag"][1:]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        with self.assertRaises(VaultError):
            Vault.open(path, MASTER)

    def test_same_inputs_different_files(self):
        path1, vault1 = make_vault(self.dir, "one")
        path2, vault2 = make_vault(self.dir, "two")
        vault1.add(RECORD, USER, PASSWORD)
        vault2.add(RECORD, USER, PASSWORD)
        with open(path1, "rb") as fh:
            blob1 = fh.read()
        with open(path2, "rb") as fh:
            blob2 = fh.read()
        self.assertNotEqual(blob1, blob2)

    def test_empty_vault_round_trips(self):
        path, _ = make_vault(self.dir)
        reopened = Vault.open(path, MASTER)
        self.assertEqual(reopened.list_names(), [])


def run_cli(tmp, script):
    proc = subprocess.run(
        [sys.executable, MANAGER, "--dir", tmp],
        input=script,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc


class CliTests(unittest.TestCase):
    def test_full_menu_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = "\n".join([
                "1", "cctest", MASTER, MASTER,   # create
                "2", "cctest", MASTER,           # sign in
                "3", RECORD, USER, PASSWORD,     # add
                "4", RECORD,                     # fetch
                "5",                             # list
                "6", RECORD,                     # delete
                "5",                             # list (empty)
                "q",
            ]) + "\n"
            proc = run_cli(tmp, script)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("New vault created and saved as: cctest.ccv",
                          proc.stdout)
            self.assertIn("Thank you, you are now signed in.", proc.stdout)
            self.assertIn("The username: is john", proc.stdout)
            self.assertIn("The password is: secretpassword", proc.stdout)
            self.assertIn("(vault is empty)", proc.stdout)
            self.assertTrue(os.path.exists(os.path.join(tmp, "cctest.ccv")))

    def test_mismatched_confirmation_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = "1\ncctest\n%s\n%s\nq\n" % (MASTER, "different")
            proc = run_cli(tmp, script)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("do not match", proc.stdout)
            self.assertFalse(os.path.exists(os.path.join(tmp, "cctest.ccv")))

    def test_operations_without_sign_in_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli(tmp, "3\n4\n5\n6\nq\n")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertGreaterEqual(
                proc.stdout.count("You are not signed in to a vault."), 4)

    def test_wrong_password_at_cli_sign_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = make_vault(tmp)
            script = "2\ncctest\nwrong-master\n4\nq\n"
            proc = run_cli(tmp, script)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Error: wrong master password", proc.stdout)
            # Still unsigned in: the fetch must refuse, not print a record.
            self.assertIn("You are not signed in to a vault.", proc.stdout)

    def test_quit_variants_and_eof(self):
        with tempfile.TemporaryDirectory() as tmp:
            for script in ("quit\n", "q\n", ""):
                proc = run_cli(tmp, script)
                self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
