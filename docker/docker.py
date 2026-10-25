#!/usr/bin/env python3
"""docker.py — a SCOPED Build-Your-Own-Docker.

Implements the challenge page's Step 1 (run a command, propagate its
exit code) and the offline, file-based parts of Steps 7-8 (parse an
image manifest, unpack layer tarballs in order with OCI whiteouts,
read an image config, run a command with the config's working
directory and environment).

This is NOT a container runtime. It creates no namespaces, performs
no chroot, mounts nothing, and sets no cgroup limits. A command run
by `run-image` still sees the host filesystem, host processes, and
host hostname, and runs with the caller's privileges; only its
working directory and environment come from the image config.
Do not use it for isolation or for running untrusted images.

Python 3 standard library only. No network access.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path


# ---------------------------------------------------------------- run
def run_command(argv):
    """Step 1: run argv with inherited stdio, return its exit code.

    A missing executable returns 127 (shell convention) instead of
    raising, so the CLI behaves like a shell. Empty argv is a
    usage error (ValueError).
    """
    if not argv:
        raise ValueError("run: no command given")
    try:
        result = subprocess.run(argv)
    except FileNotFoundError:
        print(f"run: command not found: {argv[0]}", file=sys.stderr)
        return 127
    return result.returncode


# ------------------------------------------------------- image refs
def parse_image_ref(ref):
    """Parse `registry/repo:tag` / `repo@digest` into its parts.

    Defaults: registry `docker.io`, `library/` prefix for a
    single-component repository, tag `latest`. A first component
    containing `.` or `:` (or exactly `localhost`) is a registry.
    A `@digest` sets tag to None.
    """
    if not ref:
        raise ValueError("empty image reference")
    digest = None
    if "@" in ref:
        ref, digest = ref.split("@", 1)
        if not digest:
            raise ValueError("empty digest in image reference")
    tag = "latest"
    last = ref.rsplit("/", 1)[-1]
    if ":" in last:
        ref, tag = ref.rsplit(":", 1)
        if not tag:
            raise ValueError("empty tag in image reference")
    parts = ref.split("/")
    if len(parts) == 1:
        registry, repository = "docker.io", "library/" + parts[0]
    elif "." in parts[0] or ":" in parts[0] or parts[0] == "localhost":
        registry, repository = parts[0], "/".join(parts[1:])
    else:
        registry, repository = "docker.io", ref
    if not repository or repository.startswith("/") or repository.endswith("/"):
        raise ValueError(f"invalid image reference: {ref!r}")
    if digest is not None:
        tag = None
    return {"registry": registry, "repository": repository,
            "tag": tag, "digest": digest}


# ------------------------------------------------- manifest / config
def parse_manifest(data):
    """Return {'media_type': ..., 'layers': [...]} from a manifest dict.

    Layers keep manifest order (base first). A manifest without a
    non-empty `layers` list is an error: there is nothing to unpack.
    Digest verification is NOT done (see DESIGN.md).
    """
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    layers = data.get("layers")
    if not layers:
        raise ValueError("manifest has no layers")
    return {
        "media_type": data.get("mediaType", ""),
        "layers": [
            {"media_type": layer.get("mediaType", ""),
             "digest": layer.get("digest", ""),
             "size": layer.get("size")}
            for layer in layers
        ],
    }


def parse_image_config(data):
    """Extract Env/WorkingDir/Entrypoint/Cmd from an image config dict.

    Env entries are `KEY=VALUE` strings (a bare `KEY` means "");
    later duplicates win. Missing sections default to empty.
    """
    config = data.get("config", {}) if isinstance(data, dict) else {}
    if not isinstance(config, dict):
        raise ValueError("image config 'config' must be an object")
    env = {}
    for entry in config.get("Env") or []:
        key, _, value = str(entry).partition("=")
        env[key] = value
    return {
        "env": env,
        "workdir": config.get("WorkingDir") or "",
        "entrypoint": list(config.get("Entrypoint") or []),
        "cmd": list(config.get("Cmd") or []),
    }


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------ unpack
def _safe_join(rootfs, name):
    """Join a tar member name onto rootfs, rejecting escapes.

    Leading `./` segments are stripped; absolute names and any
    `..` component that would leave the rootfs raise ValueError.
    Returns the destination Path (lexical, not resolved).
    """
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if name.startswith("/"):
        raise ValueError(f"unsafe tar member (absolute path): {name!r}")
    depth = 0
    for part in parts:
        if part == "..":
            depth -= 1
        else:
            depth += 1
        if depth < 0:
            raise ValueError(f"unsafe tar member (escapes rootfs): {name!r}")
    return Path(rootfs).joinpath(*parts) if parts else Path(rootfs)


def _is_inside(rootfs, path):
    """Lexical containment check (both sides normalised, unresolved)."""
    root = Path(os.path.normpath(rootfs))
    path = Path(os.path.normpath(path))
    return path == root or root in path.parents


def _resolve_parent(rootfs, dest):
    """Resolve symlink components of dest's parent dir, lexically.

    Walks the parent chain on disk; a symlink component is resolved
    against the rootfs (absolute targets are rootfs-relative, as in
    a container). Raises ValueError if resolution leaves the rootfs.
    Returns the resolved parent Path.
    """
    rootfs = Path(rootfs)
    cur = rootfs
    for part in dest.relative_to(rootfs).parts[:-1]:
        cur = cur / part
        if cur.is_symlink():
            target = os.readlink(cur)
            if os.path.isabs(target):
                cur = rootfs.joinpath(*[p for p in target.split("/")
                                        if p not in ("", ".")])
            else:
                cur = Path(os.path.normpath(cur.parent / target))
            if not _is_inside(rootfs, cur):
                raise ValueError(f"symlink escapes rootfs: {cur}")
    return cur


def _remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def apply_layer(rootfs, tar_path):
    """Apply one layer tarball onto rootfs, honouring OCI whiteouts.

    `.wh.<name>` deletes `<dir>/<name>`; `.wh..wh..opq` in a
    directory deletes that directory's current contents. Setuid
    and setgid bits are stripped from extracted files.
    """
    rootfs = Path(rootfs)
    rootfs.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:*") as tar:
        for member in tar:
            name = member.name
            if name in ("", ".", "./"):
                continue
            dest = _safe_join(rootfs, name)
            base = dest.name
            if base == ".wh..wh..opq":
                parent = _resolve_parent(rootfs, dest)
                if parent.is_dir():
                    for child in parent.iterdir():
                        _remove(child)
                continue
            if base.startswith(".wh."):
                target = dest.parent / base[4:]
                if target == rootfs or rootfs not in target.parents:
                    raise ValueError(f"unsafe whiteout: {name!r}")
                _remove(target)
                continue
            if member.isdir():
                _resolve_parent(rootfs, dest).mkdir(parents=True, exist_ok=True)
                dest.mkdir(exist_ok=True)
            elif member.issym() or member.islnk():
                parent = _resolve_parent(rootfs, dest)
                parent.mkdir(parents=True, exist_ok=True)
                if member.issym():
                    target = member.linkname
                    if os.path.isabs(target):
                        resolved = Path(os.path.normpath(
                            rootfs / target.lstrip("/")))
                    else:
                        resolved = Path(os.path.normpath(parent / target))
                    if resolved != rootfs and rootfs not in resolved.parents:
                        raise ValueError(
                            f"symlink escapes rootfs: {name!r} -> {target!r}")
                else:
                    src = _safe_join(rootfs, member.linkname)
                    if src != rootfs and rootfs not in src.parents:
                        raise ValueError(
                            f"hardlink escapes rootfs: {name!r}")
                if dest.exists() or dest.is_symlink():
                    _remove(dest)
                if member.issym():
                    os.symlink(member.linkname, dest)
                else:
                    os.link(_safe_join(rootfs, member.linkname), dest)
            elif member.isfile():
                parent = _resolve_parent(rootfs, dest)
                parent.mkdir(parents=True, exist_ok=True)
                src = tar.extractfile(member)
                if src is None:
                    raise ValueError(f"cannot read tar member: {name!r}")
                with open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                os.chmod(dest, member.mode & 0o1777)  # strip setuid/setgid
            # Other member types (devices, fifos, ...) are skipped:
            # creating them needs privilege and serves no scoped purpose.


def unpack_image(rootfs, manifest, layer_paths):
    """Apply layers in manifest order. layer_paths are local files."""
    if len(layer_paths) != len(manifest["layers"]):
        raise ValueError(
            f"manifest lists {len(manifest['layers'])} layers but "
            f"{len(layer_paths)} layer files were given")
    for layer_path in layer_paths:
        apply_layer(rootfs, layer_path)


# --------------------------------------------------------- run-image
def resolve_workdir(rootfs, workdir):
    """Resolve a config working directory inside rootfs (or rootfs)."""
    if not workdir or workdir == "/":
        return Path(rootfs)
    dest = _safe_join(rootfs, workdir.lstrip("/"))
    if not dest.is_dir():
        raise ValueError(f"working directory does not exist: {workdir!r}")
    return dest


def build_command(config, args):
    """Docker entrypoint/cmd semantics: args replace Cmd, not Entrypoint."""
    entrypoint = config.get("entrypoint") or []
    cmd = config.get("cmd") or []
    if args:
        return list(entrypoint) + list(args)
    if entrypoint or cmd:
        return list(entrypoint) + list(cmd)
    raise ValueError("no entrypoint/cmd in config and no command given")


def run_image(rootfs, config, args):
    """Run a command with the config's cwd and env. NOT isolated.

    See module docstring: no chroot, no namespaces, no mounts.
    Returns the command's exit code.
    """
    argv = build_command(config, args)
    cwd = resolve_workdir(rootfs, config.get("workdir") or "")
    env = dict(os.environ)
    env.update(config.get("env") or {})
    try:
        result = subprocess.run(argv, cwd=cwd, env=env)
    except FileNotFoundError:
        print(f"run-image: command not found: {argv[0]}", file=sys.stderr)
        return 127
    return result.returncode


def inspect_text(manifest, config):
    """Human-readable summary of a manifest + image config."""
    lines = [f"layers: {len(manifest['layers'])}"]
    for layer in manifest["layers"]:
        lines.append(f"  {layer['digest']} ({layer['size']})")
    if config:
        lines.append(f"workdir: {config['workdir'] or '(root)'}")
        lines.append(f"entrypoint: {' '.join(config['entrypoint']) or '(none)'}")
        lines.append(f"cmd: {' '.join(config['cmd']) or '(none)'}")
        lines.append("env:")
        for key, value in config["env"].items():
            lines.append(f"  {key}={value}")
    return "\n".join(lines)


# --------------------------------------------------------------- CLI
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="docker.py",
        description="Scoped Build-Your-Own-Docker: run, unpack and "
                    "config-run. NOT a container runtime: no namespaces, "
                    "no chroot, no mounts, no cgroups, no registry client.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Step 1: run a command, "
                           "propagate its exit code.")
    p_run.add_argument("argv", nargs=argparse.REMAINDER,
                       help="command and arguments")

    p_unpack = sub.add_parser("unpack", help="Step 7 (offline): unpack "
                              "local layer tarballs in manifest order.")
    p_unpack.add_argument("--manifest", required=True)
    p_unpack.add_argument("--config")
    p_unpack.add_argument("--rootfs", required=True)
    p_unpack.add_argument("layers", nargs="+")

    p_inspect = sub.add_parser("inspect", help="Show manifest layers "
                               "and image config.")
    p_inspect.add_argument("--manifest", required=True)
    p_inspect.add_argument("--config")

    p_runimg = sub.add_parser("run-image", help="Step 8 (config only): "
                              "run with the config's workdir and env. "
                              "NOT isolated.")
    p_runimg.add_argument("--rootfs", required=True)
    p_runimg.add_argument("--config")
    p_runimg.add_argument("argv", nargs=argparse.REMAINDER,
                          help="command overriding config Cmd")

    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            argv_list = list(args.argv)
            if argv_list and argv_list[0] == "--":
                argv_list = argv_list[1:]
            return run_command(argv_list)
        if args.command == "unpack":
            manifest = parse_manifest(load_json(args.manifest))
            if args.config:
                parse_image_config(load_json(args.config))
            unpack_image(args.rootfs, manifest, args.layers)
            return 0
        if args.command == "inspect":
            manifest = parse_manifest(load_json(args.manifest))
            config = parse_image_config(load_json(args.config)) \
                if args.config else None
            print(inspect_text(manifest, config))
            return 0
        if args.command == "run-image":
            argv_list = list(args.argv)
            if argv_list and argv_list[0] == "--":
                argv_list = argv_list[1:]
            config = parse_image_config(load_json(args.config)) \
                if args.config else {"env": {}, "workdir": "",
                                     "entrypoint": [], "cmd": []}
            return run_image(args.rootfs, config, argv_list)
    except ValueError as exc:
        print(f"docker.py: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"docker.py: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
