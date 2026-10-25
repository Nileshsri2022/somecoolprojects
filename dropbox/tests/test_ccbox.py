"""Tests for ccbox (dropbox). Each test runs its own server on an
ephemeral port with a fresh temporary data directory; the server
is shut down in tearDown, so no stray server survives the suite."""

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ccbox  # noqa: E402
from ccbox import CcboxError  # noqa: E402


class ServerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.server = ccbox.make_server(str(self.data_dir), 0)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        ccbox.signup(self.url, "alice", "correct horse")
        self.token = ccbox.login(self.url, "alice", "correct horse")["token"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    # -- auth --------------------------------------------------------
    def test_login_succeeds_for_new_user(self):
        ccbox.signup(self.url, "bob", "pw12345")
        result = ccbox.login(self.url, "bob", "pw12345")
        self.assertEqual(result["username"], "bob")
        self.assertTrue(result["token"])

    def test_duplicate_signup_rejected(self):
        with self.assertRaises(CcboxError):
            ccbox.signup(self.url, "alice", "something else")

    def test_wrong_password_rejected(self):
        with self.assertRaises(CcboxError):
            ccbox.login(self.url, "alice", "wrong")

    def test_unknown_user_rejected(self):
        with self.assertRaises(CcboxError):
            ccbox.login(self.url, "nobody", "pw")

    def test_missing_token_rejected(self):
        with self.assertRaises(CcboxError) as ctx:
            ccbox.list_dir(self.url, None)
        self.assertEqual(ctx.exception.status, 401)

    def test_bad_token_rejected(self):
        with self.assertRaises(CcboxError) as ctx:
            ccbox.list_dir(self.url, "bogus-token")
        self.assertEqual(ctx.exception.status, 401)

    def test_users_have_separate_drives(self):
        ccbox.signup(self.url, "bob", "pw12345")
        bob = ccbox.login(self.url, "bob", "pw12345")["token"]
        ccbox.upload_file(self.url, self.token,
                          _write(self.tmp, "a.txt", b"alice file"),
                          "shared-name.txt")
        listing = ccbox.list_dir(self.url, bob)
        self.assertEqual(listing["entries"], [])

    # -- folders / upload / download ---------------------------------
    def test_mkdir_and_list_nested(self):
        ccbox.mkdir(self.url, self.token, "docs/work")
        entries = ccbox.list_dir(self.url, self.token)["entries"]
        self.assertEqual([e["path"] for e in entries], ["docs"])
        sub = ccbox.list_dir(self.url, self.token, "docs")["entries"]
        self.assertEqual([e["path"] for e in sub], ["docs/work"])

    def test_upload_download_text_roundtrip(self):
        local = _write(self.tmp, "hello.txt", b"hello dropbox\n")
        ccbox.upload_file(self.url, self.token, local, "notes/hello.txt")
        out = Path(self.tmp.name) / "out.txt"
        ccbox.download_file(self.url, self.token, "notes/hello.txt", out)
        self.assertEqual(out.read_bytes(), b"hello dropbox\n")

    def test_upload_download_binary_roundtrip(self):
        blob = bytes(range(256)) * 4
        local = _write(self.tmp, "blob.bin", blob)
        ccbox.upload_file(self.url, self.token, local, "blob.bin")
        out = Path(self.tmp.name) / "blob-out.bin"
        ccbox.download_file(self.url, self.token, "blob.bin", out)
        self.assertEqual(out.read_bytes(), blob)

    def test_upload_overwrites_with_new_hash(self):
        first = _write(self.tmp, "f.txt", b"v1")
        ccbox.upload_file(self.url, self.token, first, "f.txt")
        second = _write(self.tmp, "f2.txt", b"v2 longer")
        result = ccbox.upload_file(self.url, self.token, second, "f.txt")
        self.assertNotEqual(result["sha256"],
                            ccbox.sha256_of(b"v1"))
        out = Path(self.tmp.name) / "f-out.txt"
        ccbox.download_file(self.url, self.token, "f.txt", out)
        self.assertEqual(out.read_bytes(), b"v2 longer")

    def test_download_missing_file_rejected(self):
        with self.assertRaises(CcboxError):
            ccbox.download_file(self.url, self.token, "nope.txt",
                                Path(self.tmp.name) / "x")

    def test_tree_lists_nested_files(self):
        ccbox.upload_file(self.url, self.token,
                          _write(self.tmp, "t1.txt", b"1"), "a/t1.txt")
        ccbox.upload_file(self.url, self.token,
                          _write(self.tmp, "t2.txt", b"2"), "a/b/t2.txt")
        paths = [e["path"] for e in
                 ccbox.tree(self.url, self.token)["entries"]]
        self.assertEqual(paths, ["a/b/t2.txt", "a/t1.txt"])

    def test_upload_dir_preserves_relative_paths(self):
        base = Path(self.tmp.name) / "srcdir"
        (base / "sub").mkdir(parents=True)
        (base / "top.txt").write_bytes(b"top")
        (base / "sub" / "inner.txt").write_bytes(b"inner")
        uploaded = ccbox.upload_dir(self.url, self.token, base, "pack")
        self.assertEqual(uploaded, ["pack/sub/inner.txt", "pack/top.txt"])
        paths = [e["path"] for e in
                 ccbox.tree(self.url, self.token)["entries"]]
        self.assertEqual(paths, uploaded)

    # -- path safety ---------------------------------------------------
    def test_path_traversal_rejected_on_upload(self):
        local = _write(self.tmp, "evil.txt", b"x")
        for bad in ("../escape.txt", "/abs.txt", "a/../../escape.txt"):
            with self.assertRaises(CcboxError, msg=bad):
                ccbox.upload_file(self.url, self.token, local, bad)

    def test_path_traversal_rejected_on_mkdir(self):
        with self.assertRaises(CcboxError):
            ccbox.mkdir(self.url, self.token, "../escape")

    def test_empty_path_rejected_on_upload(self):
        local = _write(self.tmp, "e.txt", b"x")
        with self.assertRaises(CcboxError):
            ccbox.upload_file(self.url, self.token, local, "")

    # -- share links ---------------------------------------------------
    def test_public_share_fetchable_without_token(self):
        ccbox.upload_file(self.url, self.token,
                          _write(self.tmp, "s.txt", b"shared"),
                          "s.txt")
        link = ccbox.create_share(self.url, self.token, "s.txt",
                                  public=True)
        result = ccbox.fetch_share(self.url, None, link["token"])
        self.assertEqual(result["path"], "s.txt")

    def test_private_share_requires_owner(self):
        ccbox.upload_file(self.url, self.token,
                          _write(self.tmp, "p.txt", b"private"),
                          "p.txt")
        link = ccbox.create_share(self.url, self.token, "p.txt",
                                  public=False)
        with self.assertRaises(CcboxError):
            ccbox.fetch_share(self.url, None, link["token"])
        ccbox.signup(self.url, "mallory", "pw12345")
        other = ccbox.login(self.url, "mallory", "pw12345")["token"]
        with self.assertRaises(CcboxError):
            ccbox.fetch_share(self.url, other, link["token"])
        ok = ccbox.fetch_share(self.url, self.token, link["token"])
        self.assertEqual(ok["path"], "p.txt")

    def test_share_of_missing_path_rejected(self):
        with self.assertRaises(CcboxError):
            ccbox.create_share(self.url, self.token, "ghost.txt",
                               public=True)

    def test_share_folder_lists_contents(self):
        ccbox.upload_file(self.url, self.token,
                          _write(self.tmp, "sf.txt", b"in folder"),
                          "folder/sf.txt")
        link = ccbox.create_share(self.url, self.token, "folder",
                                  public=True)
        result = ccbox.fetch_share(self.url, None, link["token"])
        self.assertEqual(result["type"], "folder")
        self.assertEqual([e["path"] for e in result["entries"]],
                         ["folder/sf.txt"])

    # -- delete ----------------------------------------------------------
    def test_delete_removes_file(self):
        ccbox.upload_file(self.url, self.token,
                          _write(self.tmp, "d.txt", b"bye"), "d.txt")
        ccbox.delete(self.url, self.token, "d.txt")
        with self.assertRaises(CcboxError):
            ccbox.download_file(self.url, self.token, "d.txt",
                                Path(self.tmp.name) / "d-out")

    def test_delete_missing_path_rejected(self):
        with self.assertRaises(CcboxError):
            ccbox.delete(self.url, self.token, "ghost.txt")

    # -- sync ------------------------------------------------------------
    def test_sync_uploads_local_only_file(self):
        local_dir = Path(self.tmp.name) / "sync1"
        local_dir.mkdir()
        (local_dir / "new.txt").write_bytes(b"brand new")
        result = ccbox.sync_once(self.url, self.token, local_dir)
        self.assertEqual(result["uploaded"], ["new.txt"])
        self.assertEqual(result["downloaded"], [])
        paths = [e["path"] for e in
                 ccbox.tree(self.url, self.token)["entries"]]
        self.assertEqual(paths, ["new.txt"])

    def test_sync_downloads_remote_only_file(self):
        ccbox.upload_file(self.url, self.token,
                          _write(self.tmp, "r.txt", b"remote"),
                          "remote.txt")
        local_dir = Path(self.tmp.name) / "sync2"
        result = ccbox.sync_once(self.url, self.token, local_dir)
        self.assertEqual(result["downloaded"], ["remote.txt"])
        self.assertEqual((local_dir / "remote.txt").read_bytes(), b"remote")

    def test_sync_identical_file_is_noop(self):
        local_dir = Path(self.tmp.name) / "sync3"
        local_dir.mkdir()
        target = local_dir / "same.txt"
        target.write_bytes(b"same")
        ccbox.upload_file(self.url, self.token, target, "same.txt")
        result = ccbox.sync_once(self.url, self.token, local_dir)
        self.assertEqual(result["uploaded"], [])
        self.assertEqual(result["downloaded"], [])
        self.assertEqual(result["unchanged"], ["same.txt"])

    def test_sync_uploads_locally_newer_change(self):
        local_dir = Path(self.tmp.name) / "sync4"
        local_dir.mkdir()
        target = local_dir / "chg.txt"
        target.write_bytes(b"old")
        ccbox.upload_file(self.url, self.token, target, "chg.txt",
                          mtime=1000.0)
        target.write_bytes(b"new local")
        os.utime(target, (2000.0, 2000.0))
        result = ccbox.sync_once(self.url, self.token, local_dir)
        self.assertEqual(result["uploaded"], ["chg.txt"])
        out = Path(self.tmp.name) / "chg-out.txt"
        ccbox.download_file(self.url, self.token, "chg.txt", out)
        self.assertEqual(out.read_bytes(), b"new local")

    def test_sync_downloads_remotely_newer_change(self):
        local_dir = Path(self.tmp.name) / "sync5"
        local_dir.mkdir()
        target = local_dir / "chg2.txt"
        target.write_bytes(b"local old")
        os.utime(target, (1000.0, 1000.0))
        ccbox.upload_file(self.url, self.token,
                          _write(self.tmp, "chg2r.txt", b"remote new"),
                          "chg2.txt", mtime=2000.0)
        result = ccbox.sync_once(self.url, self.token, local_dir)
        self.assertEqual(result["downloaded"], ["chg2.txt"])
        self.assertEqual(target.read_bytes(), b"remote new")

    def test_sync_does_not_propagate_deletions(self):
        ccbox.upload_file(self.url, self.token,
                          _write(self.tmp, "keep.txt", b"keep"),
                          "keep.txt")
        local_dir = Path(self.tmp.name) / "sync6"
        local_dir.mkdir()
        # Local side has no keep.txt: sync downloads it, not deletes it.
        result = ccbox.sync_once(self.url, self.token, local_dir)
        self.assertIn("keep.txt", result["downloaded"])
        paths = [e["path"] for e in
                 ccbox.tree(self.url, self.token)["entries"]]
        self.assertIn("keep.txt", paths)


def _write(tmp, name, data):
    path = Path(tmp.name) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


if __name__ == "__main__":
    unittest.main()
