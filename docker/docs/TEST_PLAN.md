# TEST_PLAN — docker (scoped)

All tests: `tests/test_docker.py`, stdlib `unittest`, temp dirs only.
Run: `python3 -m unittest discover -s tests -v` from the project dir.

## run (Step 1)

- `run echo hello` prints `hello`, exit 0.
- A command exiting 3 returns 3 (exit-code propagation).
- A nonexistent command raises/returns non-zero without crashing
  the CLI (subprocess `FileNotFoundError` → exit 127, matching
  shell convention, documented in code).
- Empty argv → usage error (exit 2 at CLI level).

## parse_image_ref

- `ubuntu` → registry `docker.io`, repository `library/ubuntu`,
  tag `latest`.
- `ubuntu:22.04` → tag `22.04`.
- `user/app:1.0` → repository `user/app`, no `library/` prefix.
- `registry.example.com:5000/ns/app@sha256:abc` → registry, repo,
  digest set, tag `None`.
- `localhost/app` → registry `localhost`.

## parse_manifest / parse_image_config

- Schema-2 manifest: layers returned in order with digests/sizes.
- Manifest without `layers` → `ValueError`.
- Config: `Env` list → dict (last wins, bare key → `""`),
  `WorkingDir`, `Entrypoint`, `Cmd` extracted; missing sections
  → empty defaults.

## unpack (Step 7 offline)

- Two layers in order: layer 2 overwrites a file from layer 1,
  adds a new file, layer-1-only file survives.
- Whiteout: `.wh.<name>` in layer 2 deletes the file layer 1 created.
- Opaque: `.wh..wh..opq` in a directory in layer 2 clears that
  directory's layer-1 contents before layer 2's files land.
- Gzipped layer tarballs unpack identically to plain tars.
- Safety: a tar with a `../evil` member and a tar with an absolute
  member are both rejected with `ValueError` and write nothing
  outside the rootfs (asserted by checking the temp parent dir).
- Safety: a symlink escaping the rootfs is rejected.
- Setuid bit on a layer file is stripped on extraction.

## inspect / run-image (Step 8 config subset)

- `inspect` CLI output lists layer count/digests and config
  env/workdir/entrypoint/cmd.
- `run-image` with a config (env `GREETING=hi`, workdir `/app`)
  runs a script inside the rootfs that prints the env var and its
  cwd; both match the config.
- `run-image` args replace `Cmd` but keep `Entrypoint` prepended.
- `run-image` with no entrypoint/cmd and no args → error, exit 2.
- `run-image` with a workdir escaping the rootfs (`/../../etc`)
  → `ValueError`, nothing runs.

## Explicitly NOT tested

- Real namespace/chroot/mount/cgroup behaviour (not implemented).
- Registry auth/download (not implemented, no network in tests).
- Running an ELF binary from inside a rootfs (host loader is used;
  documented limitation, not a test target).
