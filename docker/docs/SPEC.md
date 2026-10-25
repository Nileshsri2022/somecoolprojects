# SPEC — Build Your Own Docker (scoped)

Challenge page: https://codingchallenges.fyi/challenges/challenge-docker/
Page slug used: `challenge-docker` (first guess, no 404 — the page loaded
in full, Steps 0–8 plus "Going Further").

## What the page asks for

An application, called `ccrun` on the page, to pull a container image
from Docker Hub, unpack it, and run it in a home-grown container runtime:

- Step 0 — Set up; on non-Linux, a Linux VM; download an Alpine
  root filesystem and mark it with a file `ALPHINE_FS_ROOT` (sic).
- Step 1 — `ccrun run <command> <args>`: run an arbitrary command with
  stdin/stdout/stderr connected to the terminal, and propagate its
  exit code.
- Step 2 — Own hostname via a new UTS namespace + `sethostname`
  (via `clone`, re-execing inside the namespace).
- Step 3 — Isolate from the host filesystem via `chroot` into the
  Alpine rootfs.
- Step 4 — Isolate processes via a new PID namespace + mounting
  `/proc`, in a new mount namespace (`unshare`) so the mount does not
  leak to the host.
- Step 5 — Run rootless via a new user namespace with uid/gid mappings.
- Step 6 — Limit memory/CPU via cgroups (`/sys/fs/cgroup`).
- Step 7 — Pull an image from Docker Hub via the Registry HTTP API v2:
  authenticate, fetch the manifest, parse its layer list, fetch each
  layer, unzip layers in order (base first) to rebuild the filesystem,
  fetch and store the image config.
- Step 8 — Run the pulled image: `chroot` to the image root, apply the
  config's environment variables and working directory.
- Going Further — pull+run in one go, tag support, networking via the
  network namespace, a fresh filesystem root per invocation.

## What this build implements (scoped subset)

Only the parts that are tractable in Python 3 stdlib, without root,
without privileged namespace/mount/chroot operations, and without
network access in tests:

1. **Step 1, fully** — `run <command> [args...]`: executes the command
   with inherited stdio and propagates its exit code.
2. **Step 7, offline subset** — `unpack`: given a local manifest JSON
   (Docker schema 2 / OCI image manifest shape) and local layer
   tarballs, applies the layers in manifest order onto a rootfs
   directory, honouring OCI whiteouts (`.wh.<name>` deletes a path,
   `.wh..wh..opq` clears a directory). Layer *fetching* from a
   registry (auth token, manifest download, blob download) is NOT
   implemented — see "Not built".
3. **Step 8, config subset** — `inspect` and `run-image`: read an image
   config JSON (environment, working directory, entrypoint, command)
   and run a command with that cwd (inside the rootfs) and environment.
   This is a config-driven runner, NOT a container (see below).
4. **Image reference parsing** — `library/` default, `:latest` default
   tag, explicit registry/tag/digest handling, as the input the
   (unimplemented) registry client would need.

## What is NOT built — and must not be claimed

- **No container isolation at all.** No UTS/PID/mount/user/network
  namespace, no `chroot`, no `/proc` mount, no cgroups, no rootless
  mapping (page Steps 2–6). A command run by `run-image` still sees
  the host filesystem outside the rootfs, the host process table, the
  host hostname, and runs with the caller's privileges. The only
  things `run-image` changes are the working directory and the
  environment.
- **No registry client.** No Docker Hub authentication, manifest
  download, or layer download. `unpack` works on files already on
  disk; it never touches the network.
- **No Alpine rootfs, no ELF execution inside a rootfs.** There is no
  downloaded image here, and `run-image` cannot run a rootfs binary
  that needs the rootfs's libraries (without `chroot` the host loader
  is used). It works for host-runnable programs and for scripts whose
  interpreter resolves on the host (e.g. `#!/usr/bin/env python3`).
- **No networking, no tags/pull/run in one go, no per-invocation
  fresh rootfs copy** (Going Further items).

## CLI

```
python3 docker.py run [--] <command> [args...]
python3 docker.py unpack --manifest MANIFEST.json [--config CONFIG.json]
                         --rootfs DIR LAYER.tar[.gz]...
python3 docker.py inspect --manifest MANIFEST.json [--config CONFIG.json]
python3 docker.py run-image --rootfs DIR [--config CONFIG.json]
                            [CMD...]
```

Exit codes: the run command's exit code for `run`/`run-image`;
`2` for usage errors; `1` for unpack/inspect errors (bad manifest,
unsafe tar member, workdir escaping the rootfs).

## Safety rules (unpack)

A layer member is rejected (whole unpack aborts, no partial layer
guarantee beyond the members already written) if it is an absolute
path, contains a `..` component escaping the rootfs, or is a symlink
/ hardlink whose target escapes the rootfs. Setuid/setgid bits are
stripped when writing files. These checks are lexical (no host
filesystem is followed outside the rootfs).
