# DESIGN — docker (scoped)

## Assumptions (stated before coding, ponytail rules)

1. The sandbox forbids the honest route to Steps 2–6: privileged
   namespace creation, `chroot`, mounts, and cgroup writes could
   affect the host and must not be attempted here, and tests must not
   require root. So the build is scoped to Step 1 + the offline,
   file-based parts of Steps 7–8. Anything else would be fake
   isolation, which is worse than no isolation.
2. Python 3 stdlib only: `subprocess`, `tarfile`, `json`, `argparse`,
   `pathlib`, `os`, `shutil`. No third-party packages, no network
   calls in code or tests.
3. Single main file `docker.py`, library functions importable by
   tests (`from docker import ...`), CLI thin on top of them.
4. All tests use `tempfile.TemporaryDirectory` only; nothing writes
   outside the temp dir, nothing needs root, nothing needs network.

## Components

- `run_command(argv)` — Step 1. `subprocess.run(argv)` with
  inherited stdio; returns the child's exit code. Empty argv is a
  usage error, not a crash.
- `parse_image_ref(ref)` — splits an image reference into
  `{registry, repository, tag, digest}`. Rules: a first component
  containing `.` or `:` or equal to `localhost` is a registry,
  otherwise registry defaults to `docker.io`; a single-component
  repository gets the `library/` prefix; a trailing `:tag` after the
  last `/` is the tag, default `latest`; `@digest` overrides the tag
  (tag becomes `None`).
- `parse_manifest(data)` — accepts a parsed manifest dict; returns
  `{media_type, layers}` where each layer is `{media_type, digest,
  size}` from the `layers` list, in order. Missing/empty `layers`
  is an error: a manifest without layers has nothing to unpack.
- `parse_image_config(data)` — reads the `config` object of an image
  config JSON: `Env` (`KEY=VALUE` strings → dict, last wins, a bare
  `KEY` means empty value), `WorkingDir`, `Entrypoint`, `Cmd`.
  Missing sections default to empty.
- `apply_layer(rootfs, tar_path)` — opens the tarball with
  `tarfile` (handles plain tar and gzip transparently) and applies
  members in archive order. Regular files are written with mode
  `& 0o777` minus setuid/setgid bits; directories are created;
  symlinks/hardlinks are created only if their target stays inside
  the rootfs. Whiteouts: a member basename `.wh.<name>` deletes
  `<dir>/<name>`; a member named `.wh..wh..opq` in a directory
  deletes everything currently in that directory. Members are
  validated before being written (see SPEC safety rules).
- `unpack_image(rootfs, manifest, layer_paths)` — applies layers in
  manifest order. Note: it does NOT verify digests against the
  manifest (no hashes are computed) — documented divergence, since
  verifying a digest requires the exact blob bytes and adds nothing
  to the layer-application behaviour being tested.
- `resolve_workdir(rootfs, workdir)` — resolves a config working
  directory inside the rootfs; rejects absolute escapes and `..`
  escapes with `ValueError`. An empty workdir means the rootfs root.
- `build_command(config, args)` — Docker entrypoint/cmd semantics:
  if the caller supplies args they replace `Cmd` but `Entrypoint`
  is still prepended; with no args, `Entrypoint + Cmd` is used;
  with neither, an error.
- `run_image(rootfs, config, args)` — runs `build_command(...)` with
  `cwd=resolve_workdir(...)` and env = caller env overridden by
  config `Env`. Returns the exit code. Explicitly NOT chrooted.

## Divergences from the page, recorded

- `ccrun` is named `docker.py` here (project directory convention);
  the subcommand vocabulary (`run`, `unpack`, `inspect`,
  `run-image`) is this project's, not the page's.
- No registry HTTP, no digest verification, no Alpine rootfs, no
  namespaces/chroot/mounts/cgroups (see SPEC.md "Not built").
- `unpack` takes layer files on the command line rather than
  deriving them from manifest digests, because there is no local
  blob store; the manifest's layer *order* is what is honoured.
- `run-image` documents its non-isolation in its `--help` text and
  in the README, so a user cannot mistake it for a container.

## Success criteria (verifiable)

- `python3 -m unittest discover -s tests -v` passes, all tests in
  temp dirs, no root, no network.
- `python3 docker.py run echo Hello` prints `Hello`, exit 0;
  a failing command's exit code propagates.
- A two-layer fixture unpacks in order, with overwrite, whiteout,
  and opaque-directory behaviour, and a malicious tar is rejected
  without writing outside the rootfs.
- `run-image` runs a script inside a rootfs with the config's env
  and working directory applied.
