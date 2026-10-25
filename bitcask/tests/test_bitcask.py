import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bitcask import Bitcask  # noqa: E402


class BitcaskTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self._tmp.name, "db")

    def tearDown(self):
        self._tmp.cleanup()

    def open(self, **kw):
        return Bitcask(self.dir, **kw)

    def test_put_get_missing(self):
        with self.open() as db:
            self.assertIsNone(db.get("nope"))
            db.put("Key", "Value")
            self.assertEqual(db.get("Key"), b"Value")
            self.assertIsNone(db.get("other"))

    def test_overwrite(self):
        with self.open() as db:
            db.put("k", "old")
            db.put("k", "new")
            self.assertEqual(db.get("k"), b"new")

    def test_empty_value_is_not_deleted(self):
        with self.open() as db:
            db.put("k", "")
            self.assertEqual(db.get("k"), b"")

    def test_binary_keys_values(self):
        with self.open() as db:
            db.put(b"\x00\xffkey", b"\x00\x01\xfe binary")
            self.assertEqual(db.get(b"\x00\xffkey"), b"\x00\x01\xfe binary")

    def test_delete_and_reput(self):
        with self.open() as db:
            db.delete("missing")  # no-op
            db.put("k", "v")
            db.delete("k")
            self.assertIsNone(db.get("k"))
            self.assertNotIn(b"k", db.keys())
            db.put("k", "again")
            self.assertEqual(db.get("k"), b"again")

    def test_rotation_spans_files(self):
        with self.open(max_file_size=100) as db:
            for i in range(20):
                db.put("key%02d" % i, "value-%02d" % i)
            files = sorted(n for n in os.listdir(self.dir)
                           if n.startswith("cask.") and not n.endswith(".hint"))
            self.assertGreaterEqual(len(files), 3)
            for i in range(20):
                self.assertEqual(db.get("key%02d" % i),
                                 ("value-%02d" % i).encode())

    def test_reopen_after_close(self):
        with self.open() as db:
            db.put("a", "1")
            db.put("b", "2")
            db.delete("b")
        with self.open() as db:
            self.assertEqual(db.get("a"), b"1")
            self.assertIsNone(db.get("b"))
            db.put("c", "3")
        with self.open() as db:
            self.assertEqual(db.get("c"), b"3")

    def test_crash_torn_tail_recovery(self):
        with self.open() as db:
            db.put("good", "yes")
        # Simulate a crash mid-write: garbage appended to the active log.
        active = sorted(n for n in os.listdir(self.dir)
                        if n.startswith("cask."))[ -1]
        with open(os.path.join(self.dir, active), "ab") as f:
            f.write(b"\xde\xad\xbe\xefpartial")
        with self.open() as db:
            self.assertEqual(db.get("good"), b"yes")
            db.put("after", "crash")
            self.assertEqual(db.get("after"), b"crash")
        with self.open() as db:
            self.assertEqual(db.get("good"), b"yes")
            self.assertEqual(db.get("after"), b"crash")

    def test_crc_corruption_drops_record(self):
        with self.open() as db:
            db.put("k", "original")
            db.put("k", "updated")
        # Corrupt the newest record's value byte in the active file.
        active = sorted(n for n in os.listdir(self.dir)
                        if n.startswith("cask."))[-1]
        path = os.path.join(self.dir, active)
        with open(path, "r+b") as f:
            data = bytearray(f.read())
            # Flip a byte near the end (inside the newest value).
            data[-1] ^= 0xFF
            f.seek(0)
            f.write(data)
        with self.open() as db:
            # Corrupt record dropped; older live copy is NOT resurrected
            # by this implementation's scan order? The older record was
            # scanned first, then the corrupt one stops the scan, so
            # the keydir still holds the older entry... check either
            # outcome is safe: value must be old or None, never corrupt.
            self.assertIn(db.get("k"), (b"original", None))
            db.put("k", "fixed")
            self.assertEqual(db.get("k"), b"fixed")

    def test_tombstone_survives_reopen(self):
        with self.open() as db:
            db.put("k", "v")
            db.delete("k")
        with self.open() as db:
            self.assertIsNone(db.get("k"))

    def test_merge_keeps_live_drops_dead(self):
        with self.open(max_file_size=100) as db:
            for i in range(10):
                db.put("k%d" % i, "v%d" % i)
            for i in range(5):  # overwrite half
                db.put("k%d" % i, "new%d" % i)
            db.delete("k9")
            db.put("active-only", "stay")
            before = sorted(n for n in os.listdir(self.dir)
                            if n.startswith("cask.") and not n.endswith(".hint"))
            self.assertGreaterEqual(len(before), 2)
            # All but the highest-id file are immutable and must go.
            immutable_before = before[:-1]
            db.merge()
            for i in range(5):
                self.assertEqual(db.get("k%d" % i), ("new%d" % i).encode())
            for i in range(5, 9):
                self.assertEqual(db.get("k%d" % i), ("v%d" % i).encode())
            self.assertIsNone(db.get("k9"))
            self.assertEqual(db.get("active-only"), b"stay")
            # Old immutable files gone (merged files replace them, so
            # the total count may coincidentally stay the same).
            remaining = [n for n in os.listdir(self.dir)
                         if n.startswith("cask.") and not n.endswith(".hint")]
            for name in immutable_before:
                self.assertNotIn(name, remaining)
            hints = [n for n in os.listdir(self.dir) if n.endswith(".hint")]
            self.assertGreaterEqual(len(hints), 1)
        # Reopen after merge: hint replay path must return all values.
        with self.open() as db:
            for i in range(5):
                self.assertEqual(db.get("k%d" % i), ("new%d" % i).encode())
            self.assertEqual(db.get("active-only"), b"stay")
            self.assertIsNone(db.get("k9"))

    def test_post_merge_overwrite_survives_reopen(self):
        # Merged files get ids above the active id, so a post-merge
        # overwrite in the active file must still win after reopen,
        # and a later rotation must not clobber a merged file.
        with self.open(max_file_size=100) as db:
            for i in range(10):
                db.put("k%d" % i, "v%d" % i)
            db.merge()
            db.put("k0", "post-merge")
            for i in range(10):
                db.put("fill%d" % i, "x" * 40)  # force rotation
            self.assertEqual(db.get("k0"), b"post-merge")
            for i in range(1, 10):
                self.assertEqual(db.get("k%d" % i), ("v%d" % i).encode())
        with self.open() as db:
            self.assertEqual(db.get("k0"), b"post-merge")
            for i in range(1, 10):
                self.assertEqual(db.get("k%d" % i), ("v%d" % i).encode())

    def test_merge_no_immutable_is_noop(self):
        with self.open() as db:
            db.put("k", "v")
            before = sorted(os.listdir(self.dir))
            db.merge()
            after = sorted(os.listdir(self.dir))
            self.assertEqual(before, after)
            self.assertEqual(db.get("k"), b"v")

    def test_second_opener_rejected(self):
        db1 = self.open()
        try:
            with self.assertRaises(RuntimeError):
                self.open()
        finally:
            db1.close()

    def test_use_after_close_and_idempotent_close(self):
        db = self.open()
        db.put("k", "v")
        db.close()
        db.close()  # idempotent
        with self.assertRaises(ValueError):
            db.get("k")
        with self.assertRaises(ValueError):
            db.put("k", "v")

    def test_context_manager(self):
        with self.open() as db:
            db.put("k", "v")
        with self.open() as db:
            self.assertEqual(db.get("k"), b"v")


class CliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self._tmp.name, "db")
        self.script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "bitcask.py")

    def tearDown(self):
        self._tmp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, self.script, "-db", self.dir, *args],
                              capture_output=True, text=True, timeout=30)

    def test_cli_set_get_del_merge_list(self):
        self.assertEqual(self.cli("get", "Key").stdout.strip(), "(nil)")
        self.assertEqual(self.cli("set", "Key", "Value").returncode, 0)
        self.assertEqual(self.cli("get", "Key").stdout.strip(), "Value")
        self.assertEqual(self.cli("list").stdout.strip(), "Key")
        self.assertEqual(self.cli("del", "Key").returncode, 0)
        self.assertEqual(self.cli("get", "Key").stdout.strip(), "(nil)")
        self.assertEqual(self.cli("list").stdout.strip(), "")
        self.assertEqual(self.cli("merge").returncode, 0)


if __name__ == "__main__":
    unittest.main()
