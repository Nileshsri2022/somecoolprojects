"""Tests for git_client.py. Every repo lives in a temp dir; system
git is used only as an oracle (skipped when absent), never by the
implementation under test."""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import git_client

GIT = shutil.which("git")
GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull,
               GIT_CONFIG_SYSTEM=os.devnull)


def run_cli(cwd, *args, env=None):
    """Run git_client.main in-process with cwd switched; capture out."""
    import io
    from contextlib import redirect_stdout, redirect_stderr
    old = os.getcwd()
    out, err = io.StringIO(), io.StringIO()
    try:
        os.chdir(cwd)
        with redirect_stdout(out), redirect_stderr(err):
            code = git_client.main(list(args))
    finally:
        os.chdir(old)
    return code, out.getvalue(), err.getvalue()


def git_oracle(cwd, *args):
    return subprocess.run([GIT] + list(args), cwd=cwd, env=GIT_ENV,
                          capture_output=True, text=True, timeout=30)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def init(self, name="repo"):
        path = os.path.join(self.dir, name)
        os.makedirs(path)
        code, out, err = run_cli(self.dir, "init", name)
        self.assertEqual(code, 0, err)
        self.assertIn("initialized empty repository", out)
        return path

    def add_commit(self, repo, message, files=None):
        if files:
            for rel, content in files.items():
                full = os.path.join(repo, rel)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w") as f:
                    f.write(content)
                code, _, err = run_cli(repo, "add", rel)
                self.assertEqual(code, 0, err)
        code, out, err = run_cli(repo, "commit", message)
        self.assertEqual(code, 0, err)
        return out.strip().rsplit(": ", 1)[-1]


class TestInit(Base):
    def test_layout_and_double_init(self):
        repo = self.init()
        gd = os.path.join(repo, ".git")
        for p in ("HEAD", "config", "description", "info/exclude"):
            self.assertTrue(os.path.isfile(os.path.join(gd, p)), p)
        for p in ("hooks", "objects", "refs/heads", "refs/tags"):
            self.assertTrue(os.path.isdir(os.path.join(gd, p)), p)
        with open(os.path.join(gd, "HEAD")) as f:
            self.assertEqual(f.read(), "ref: refs/heads/master\n")
        code, _, err = run_cli(repo, "init")
        self.assertNotEqual(code, 0)
        self.assertIn("already exists", err)

    @unittest.skipUnless(GIT, "git oracle not available")
    def test_git_status_oracle(self):
        repo = self.init()
        r = git_oracle(repo, "status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("On branch master", r.stdout)


class TestObjects(Base):
    def test_hash_object_known_value(self):
        repo = self.init()
        target = os.path.join(repo, "hello.txt")
        with open(target, "wb") as f:
            f.write(b"hello\n")
        expected = hashlib.sha1(b"blob 6\0hello\n").hexdigest()
        code, out, err = run_cli(repo, "hash-object", "hello.txt")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), expected)
        # No object written without -w.
        self.assertFalse(os.path.exists(
            os.path.join(repo, ".git", "objects", expected[:2], expected[2:])))
        code, out, err = run_cli(repo, "hash-object", "-w", "hello.txt")
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(
            os.path.join(repo, ".git", "objects", expected[:2], expected[2:])))

    @unittest.skipUnless(GIT, "git oracle not available")
    def test_hash_object_matches_git(self):
        repo = self.init()
        with open(os.path.join(repo, "f.txt"), "wb") as f:
            f.write(b"coding challenges\n")
        _, out, _ = run_cli(repo, "hash-object", "f.txt")
        r = git_oracle(repo, "hash-object", "f.txt")
        self.assertEqual(out.strip(), r.stdout.strip())

    def test_object_roundtrip_and_corrupt(self):
        repo = self.init()
        gd = os.path.join(repo, ".git")
        sha = git_client.write_object(gd, "blob", b"abc")
        self.assertEqual(git_client.read_object(gd, sha), ("blob", b"abc"))
        # Writing again is a no-op, not an error.
        self.assertEqual(git_client.write_object(gd, "blob", b"abc"), sha)
        # Corrupt it: read must fail.
        path = git_client.object_path(gd, sha)
        with open(path, "wb") as f:
            f.write(b"not zlib")
        with self.assertRaises(git_client.GitError):
            git_client.read_object(gd, sha)
        with self.assertRaises(git_client.GitError):
            git_client.read_object(gd, "0" * 40)


class TestAddStatus(Base):
    def test_add_and_index_contents(self):
        repo = self.init()
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("A\n")
        code, _, err = run_cli(repo, "add", "a.txt")
        self.assertEqual(code, 0, err)
        gd = os.path.join(repo, ".git")
        index = git_client.read_index(gd)
        self.assertIn("a.txt", index)
        self.assertEqual(index["a.txt"].sha,
                         hashlib.sha1(b"blob 2\0A\n").hexdigest())
        self.assertEqual(index["a.txt"].mode, "100644")

    def test_add_directory_and_nested(self):
        repo = self.init()
        for rel in ("sub/dir/f.txt", "sub/g.txt", "top.txt"):
            full = os.path.join(repo, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(rel + "\n")
        code, _, err = run_cli(repo, "add", "sub")
        self.assertEqual(code, 0, err)
        index = git_client.read_index(os.path.join(repo, ".git"))
        self.assertIn("sub/dir/f.txt", index)
        self.assertIn("sub/g.txt", index)
        self.assertNotIn("top.txt", index)

    @unittest.skipUnless(GIT, "git oracle not available")
    def test_git_status_oracle_after_add(self):
        repo = self.init()
        with open(os.path.join(repo, "hello-coding-challenges.txt"), "w") as f:
            f.write("")
        run_cli(repo, "add", "hello-coding-challenges.txt")
        r = git_oracle(repo, "status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("new file:", r.stdout)
        self.assertIn("hello-coding-challenges.txt", r.stdout)

    def test_status_sections(self):
        repo = self.init()
        with open(os.path.join(repo, "tracked.txt"), "w") as f:
            f.write("one\n")
        run_cli(repo, "add", "tracked.txt")
        with open(os.path.join(repo, "untracked.txt"), "w") as f:
            f.write("u\n")
        _, out, _ = run_cli(repo, "status")
        self.assertIn("Changes to be committed:", out)
        self.assertIn("new file:   tracked.txt", out)
        self.assertIn("Untracked files:", out)
        self.assertIn("untracked.txt", out)
        # Modify the tracked file: unstaged section appears.
        with open(os.path.join(repo, "tracked.txt"), "a") as f:
            f.write("two\n")
        _, out, _ = run_cli(repo, "status")
        self.assertIn("Changes not staged for commit:", out)
        self.assertIn("modified:   tracked.txt", out)
        # Delete it: unstaged deleted.
        os.remove(os.path.join(repo, "tracked.txt"))
        _, out, _ = run_cli(repo, "status")
        self.assertIn("deleted:   tracked.txt", out)

    def test_status_clean_after_commit(self):
        repo = self.init()
        self.add_commit(repo, "first", {"f.txt": "hi\n"})
        _, out, _ = run_cli(repo, "status")
        self.assertIn("working tree clean", out)


class TestCommitLog(Base):
    def test_commit_and_parent(self):
        repo = self.init()
        sha1 = self.add_commit(repo, "first commit", {"f.txt": "v1\n"})
        gd = os.path.join(repo, ".git")
        with open(os.path.join(gd, "refs", "heads", "master")) as f:
            self.assertEqual(f.read().strip(), sha1)
        obj_type, data = git_client.read_object(gd, sha1)
        self.assertEqual(obj_type, "commit")
        headers, msg = git_client.parse_commit(data)
        self.assertNotIn("parent", headers)
        self.assertEqual(msg.strip(), "first commit")
        with open(os.path.join(repo, "f.txt"), "w") as f:
            f.write("v2\n")
        run_cli(repo, "add", "f.txt")
        sha2 = self.add_commit(repo, "second commit")
        _, data2 = git_client.read_object(gd, sha2)
        headers2, _ = git_client.parse_commit(data2)
        self.assertEqual(headers2["parent"], [sha1])

    def test_commit_nothing_staged_fails(self):
        repo = self.init()
        code, _, err = run_cli(repo, "commit", "empty")
        self.assertNotEqual(code, 0)
        self.add_commit(repo, "one", {"f.txt": "x\n"})
        code, _, err = run_cli(repo, "commit", "again")
        self.assertNotEqual(code, 0)
        self.assertIn("nothing to commit", err)

    @unittest.skipUnless(GIT, "git oracle not available")
    def test_git_log_oracle(self):
        repo = self.init()
        self.add_commit(repo, "Add Hello CC", {"hello.txt": "Hello\n"})
        r = git_oracle(repo, "log", "--format=%s")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "Add Hello CC")
        r = git_oracle(repo, "ls-tree", "HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("hello.txt", r.stdout)

    @unittest.skipUnless(GIT, "git oracle not available")
    def test_nested_tree_oracle(self):
        repo = self.init()
        self.add_commit(repo, "nested",
                        {"sub/dir/f.txt": "deep\n", "a.txt": "top\n"})
        r = git_oracle(repo, "ls-tree", "-r", "HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sub/dir/f.txt", r.stdout)
        self.assertIn("a.txt", r.stdout)

    def test_log_order_and_content(self):
        repo = self.init()
        self.add_commit(repo, "first", {"f.txt": "1\n"})
        with open(os.path.join(repo, "f.txt"), "w") as f:
            f.write("2\n")
        run_cli(repo, "add", "f.txt")
        self.add_commit(repo, "second")
        _, out, _ = run_cli(repo, "log")
        self.assertIn("Author:", out)
        self.assertIn("Date:", out)
        self.assertLess(out.index("second"), out.index("first"))

    def test_cat_file(self):
        repo = self.init()
        sha = self.add_commit(repo, "msg", {"f.txt": "content\n"})
        gd = os.path.join(repo, ".git")
        headers, _ = git_client.parse_commit(git_client.read_object(gd, sha)[1])
        tree_sha = headers["tree"][0]
        blob_sha = git_client.read_index(gd)["f.txt"].sha
        code, out, _ = run_cli(repo, "cat-file", "-t", blob_sha)
        self.assertEqual(out.strip(), "blob")
        code, out, _ = run_cli(repo, "cat-file", "-p", blob_sha)
        self.assertEqual(out, "content\n")
        code, out, _ = run_cli(repo, "cat-file", "-p", tree_sha)
        self.assertIn("100644 blob %s\tf.txt" % blob_sha, out)
        code, out, _ = run_cli(repo, "cat-file", "-t", sha)
        self.assertEqual(out.strip(), "commit")
        code, _, err = run_cli(repo, "cat-file", "-p", "0" * 40)
        self.assertNotEqual(code, 0)


class TestDiffCheckout(Base):
    def test_diff_unstaged(self):
        repo = self.init()
        self.add_commit(repo, "base", {"f.txt": "line1\n"})
        with open(os.path.join(repo, "f.txt"), "a") as f:
            f.write("line2\n")
        _, out, _ = run_cli(repo, "diff")
        self.assertIn("diff --git a/f.txt b/f.txt", out)
        self.assertIn("--- a/f.txt", out)
        self.assertIn("+++ b/f.txt", out)
        self.assertIn("+line2", out)
        # Untracked files are not shown.
        with open(os.path.join(repo, "new.txt"), "w") as f:
            f.write("x\n")
        _, out, _ = run_cli(repo, "diff")
        self.assertNotIn("new.txt", out)

    def test_diff_cached(self):
        repo = self.init()
        self.add_commit(repo, "base", {"f.txt": "v1\n"})
        with open(os.path.join(repo, "f.txt"), "w") as f:
            f.write("v2\n")
        run_cli(repo, "add", "f.txt")
        _, out, _ = run_cli(repo, "diff", "--cached")
        self.assertIn("+v2", out)
        self.assertIn("-v1", out)
        _, out, _ = run_cli(repo, "diff")
        self.assertEqual(out, "")  # nothing unstaged

    def test_checkout_commit(self):
        repo = self.init()
        sha1 = self.add_commit(repo, "v1", {"f.txt": "one\n"})
        with open(os.path.join(repo, "f.txt"), "w") as f:
            f.write("two\n")
        run_cli(repo, "add", "f.txt")
        self.add_commit(repo, "v2")
        code, _, err = run_cli(repo, "checkout", sha1)
        self.assertEqual(code, 0, err)
        with open(os.path.join(repo, "f.txt")) as f:
            self.assertEqual(f.read(), "one\n")
        # HEAD is detached at sha1.
        with open(os.path.join(repo, ".git", "HEAD")) as f:
            self.assertEqual(f.read().strip(), sha1)
        code, _, err = run_cli(repo, "checkout", "master")
        self.assertEqual(code, 0, err)
        with open(os.path.join(repo, "f.txt")) as f:
            self.assertEqual(f.read(), "two\n")

    def test_checkout_dashdash_file(self):
        repo = self.init()
        self.add_commit(repo, "base", {"f.txt": "staged\n"})
        with open(os.path.join(repo, "f.txt"), "w") as f:
            f.write("ruined\n")
        code, _, err = run_cli(repo, "checkout", "--", "f.txt")
        self.assertEqual(code, 0, err)
        with open(os.path.join(repo, "f.txt")) as f:
            self.assertEqual(f.read(), "staged\n")
        code, _, err = run_cli(repo, "checkout", "--", "nope.txt")
        self.assertNotEqual(code, 0)

    def test_push_not_implemented(self):
        repo = self.init()
        code, _, err = run_cli(repo, "push")
        self.assertNotEqual(code, 0)
        self.assertIn("not implemented", err)


if __name__ == "__main__":
    unittest.main()
