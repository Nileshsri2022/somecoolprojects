"""Tests for docker.py (scoped Build-Your-Own-Docker).

Temp directories only; no root, no network, no host modification.
"""

import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import docker  # noqa: E402


def make_tar(path, members):
    """members: list of (name, bytes|None, kind, linkname, mode).

    kind: 'file' (bytes), 'dir', 'symlink' (linkname), 'whiteout'
    (a file named as given, e.g. '.wh.foo').
    """
    mode = "w:gz" if str(path).endswith(".gz") else "w"
    with tarfile.open(path, mode) as tar:
        for name, data, kind, linkname, fmode in members:
            info = tarfile.TarInfo(name)
            info.mode = fmode if fmode is not None else 0o644
            if kind == "dir":
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = linkname
                tar.addfile(info)
            else:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))


MANIFEST = {"schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "layers": [{"mediaType": "application/vnd.docker.image.rootfs.diff.tar",
                        "digest": "sha256:aaa", "size": 1},
                       {"mediaType": "application/vnd.docker.image.rootfs.diff.tar",
                        "digest": "sha256:bbb", "size": 2}]}

CONFIG = {"config": {"Env": ["GREETING=hi", "EMPTY", "GREETING=bye"],
                     "WorkingDir": "/app",
                     "Entrypoint": ["python3", "entry.py"],
                     "Cmd": ["default"]}}


class TestRun(unittest.TestCase):
    def test_echo(self):
        out = subprocess.run([sys.executable, "docker.py", "run",
                              "echo", "hello"], cwd=Path(__file__).parent.parent,
                             capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "hello")
        self.assertEqual(out.returncode, 0)

    def test_exit_code_propagates(self):
        self.assertEqual(docker.run_command(
            [sys.executable, "-c", "import sys; sys.exit(3)"]), 3)

    def test_missing_command_is_127(self):
        self.assertEqual(docker.run_command(["definitely-not-a-real-cmd-xyz"]),
                         127)

    def test_empty_argv_is_usage_error(self):
        with self.assertRaises(ValueError):
            docker.run_command([])


class TestImageRef(unittest.TestCase):
    def test_bare_name(self):
        self.assertEqual(docker.parse_image_ref("ubuntu"),
                         {"registry": "docker.io", "repository": "library/ubuntu",
                          "tag": "latest", "digest": None})

    def test_tag(self):
        ref = docker.parse_image_ref("ubuntu:22.04")
        self.assertEqual((ref["repository"], ref["tag"]),
                         ("library/ubuntu", "22.04"))

    def test_namespaced(self):
        ref = docker.parse_image_ref("user/app:1.0")
        self.assertEqual((ref["registry"], ref["repository"]),
                         ("docker.io", "user/app"))

    def test_registry_and_digest(self):
        ref = docker.parse_image_ref(
            "registry.example.com:5000/ns/app@sha256:abc")
        self.assertEqual(ref["registry"], "registry.example.com:5000")
        self.assertEqual(ref["repository"], "ns/app")
        self.assertEqual(ref["digest"], "sha256:abc")
        self.assertIsNone(ref["tag"])

    def test_localhost(self):
        self.assertEqual(docker.parse_image_ref("localhost/app")["registry"],
                         "localhost")


class TestManifestConfig(unittest.TestCase):
    def test_manifest_layers_in_order(self):
        parsed = docker.parse_manifest(MANIFEST)
        self.assertEqual([layer["digest"] for layer in parsed["layers"]],
                         ["sha256:aaa", "sha256:bbb"])

    def test_manifest_without_layers(self):
        with self.assertRaises(ValueError):
            docker.parse_manifest({"schemaVersion": 2})

    def test_config_parsing(self):
        cfg = docker.parse_image_config(CONFIG)
        # Last Env duplicate wins; bare key means "".
        self.assertEqual(cfg["env"]["GREETING"], "bye")
        self.assertEqual(cfg["env"]["EMPTY"], "")
        self.assertEqual(cfg["workdir"], "/app")
        self.assertEqual(cfg["entrypoint"], ["python3", "entry.py"])
        self.assertEqual(cfg["cmd"], ["default"])

    def test_config_defaults(self):
        self.assertEqual(docker.parse_image_config({}),
                         {"env": {}, "workdir": "", "entrypoint": [], "cmd": []})


class TestUnpack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "rootfs"

    def tearDown(self):
        self.tmp.cleanup()

    def test_layers_apply_in_order_with_overwrite(self):
        layer1 = Path(self.tmp.name) / "l1.tar"
        layer2 = Path(self.tmp.name) / "l2.tar.gz"
        make_tar(layer1, [("a.txt", b"one", "file", None, None),
                          ("keep.txt", b"keep", "file", None, None)])
        make_tar(layer2, [("a.txt", b"two", "file", None, None),
                          ("b.txt", b"new", "file", None, None)])
        docker.unpack_image(self.root, docker.parse_manifest(MANIFEST),
                            [layer1, layer2])
        self.assertEqual((self.root / "a.txt").read_bytes(), b"two")
        self.assertEqual((self.root / "b.txt").read_bytes(), b"new")
        self.assertEqual((self.root / "keep.txt").read_bytes(), b"keep")

    def test_whiteout_deletes(self):
        layer1 = Path(self.tmp.name) / "l1.tar"
        layer2 = Path(self.tmp.name) / "l2.tar"
        make_tar(layer1, [("gone.txt", b"x", "file", None, None)])
        make_tar(layer2, [(".wh.gone.txt", b"", "file", None, None)])
        docker.unpack_image(self.root, docker.parse_manifest(MANIFEST),
                            [layer1, layer2])
        self.assertFalse((self.root / "gone.txt").exists())

    def test_opaque_clears_directory(self):
        layer1 = Path(self.tmp.name) / "l1.tar"
        layer2 = Path(self.tmp.name) / "l2.tar"
        make_tar(layer1, [("dir/old.txt", b"old", "file", None, None)])
        make_tar(layer2, [("dir/.wh..wh..opq", b"", "file", None, None),
                          ("dir/new.txt", b"new", "file", None, None)])
        docker.unpack_image(self.root, docker.parse_manifest(MANIFEST),
                            [layer1, layer2])
        self.assertFalse((self.root / "dir" / "old.txt").exists())
        self.assertEqual((self.root / "dir" / "new.txt").read_bytes(), b"new")

    def test_path_traversal_rejected_and_writes_nothing_outside(self):
        layer = Path(self.tmp.name) / "evil.tar"
        make_tar(layer, [("../evil.txt", b"evil", "file", None, None)])
        with self.assertRaises(ValueError):
            docker.apply_layer(self.root, layer)
        self.assertFalse((Path(self.tmp.name) / "evil.txt").exists())

    def test_absolute_member_rejected(self):
        layer = Path(self.tmp.name) / "abs.tar"
        make_tar(layer, [("/tmp/abs.txt", b"x", "file", None, None)])
        with self.assertRaises(ValueError):
            docker.apply_layer(self.root, layer)

    def test_escaping_symlink_rejected(self):
        layer = Path(self.tmp.name) / "link.tar"
        make_tar(layer, [("link", None, "symlink", "../../etc", None)])
        with self.assertRaises(ValueError):
            docker.apply_layer(self.root, layer)

    def test_setuid_stripped(self):
        layer = Path(self.tmp.name) / "suid.tar"
        make_tar(layer, [("prog", b"x", "file", None, 0o4755)])
        docker.apply_layer(self.root, layer)
        mode = stat.S_IMODE((self.root / "prog").stat().st_mode)
        self.assertEqual(mode, 0o755)


class TestRunImage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "rootfs"
        app = self.root / "app"
        app.mkdir(parents=True)
        (app / "entry.py").write_text(
            "import os, sys\n"
            "print(os.environ.get('GREETING'))\n"
            "print(os.getcwd())\n"
            "print(sys.argv[1:])\n")
        (app / "entry.py").chmod(0o755)
        self.cfg = docker.parse_image_config(CONFIG)

    def tearDown(self):
        self.tmp.cleanup()

    def test_env_workdir_and_entrypoint(self):
        # Verify via a captured subprocess using a config file on disk
        # (the library run inherits stdio, so it cannot be captured here).
        cfg_path = Path(self.tmp.name) / "config.json"
        cfg_path.write_text(json.dumps(CONFIG))
        proc = subprocess.run(
            [sys.executable, "docker.py", "run-image", "--rootfs",
             str(self.root), "--config", str(cfg_path)],
            cwd=Path(__file__).parent.parent, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        lines = proc.stdout.splitlines()
        self.assertEqual(lines[0], "bye")          # config Env applied
        self.assertEqual(lines[1], str(self.root / "app"))  # workdir applied
        self.assertEqual(lines[2], "['default']")  # Cmd after Entrypoint

    def test_args_replace_cmd_keep_entrypoint(self):
        self.assertEqual(docker.build_command(self.cfg, ["custom"]),
                         ["python3", "entry.py", "custom"])

    def test_no_command_is_error(self):
        with self.assertRaises(ValueError):
            docker.build_command({"entrypoint": [], "cmd": []}, [])

    def test_escaping_workdir_rejected(self):
        with self.assertRaises(ValueError):
            docker.resolve_workdir(self.root, "/../../etc")

    def test_inspect_output(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            print(docker.inspect_text(docker.parse_manifest(MANIFEST),
                                      self.cfg))
        text = buf.getvalue()
        self.assertIn("layers: 2", text)
        self.assertIn("sha256:aaa", text)
        self.assertIn("GREETING=bye", text)
        self.assertIn("/app", text)


if __name__ == "__main__":
    unittest.main()
