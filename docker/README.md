# docker — Build Your Own Docker (SCOPED)

Coding Challenges entry 71, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

**Honest scope warning: this is NOT a container runtime.** It
implements the challenge page's Step 1 (run a command, propagate
its exit code) and the offline, file-based parts of Steps 7–8
(parse an image manifest, unpack layer tarballs in order with
OCI whiteouts, read an image config, run a command with the
config's working directory and environment). It does **not**
implement namespaces, `chroot`, mounts, cgroups, rootless user
mappings, or any Docker Hub registry client. A command run by
`run-image` still sees the host filesystem, host processes, and
host hostname, and runs with your privileges — only its working
directory and environment are set from the image config. Do not
use it for isolation or for running untrusted images.

## Usage

```sh
# Step 1: run a command, exit code propagates
python3 docker.py run echo Hello Coding Challenges!
python3 docker.py run ls madeupdir; echo $?
# -> 1 (or 2 on some systems' ls; the child's code is what is returned)

# Step 7 (offline): unpack layers from a local manifest, in order
python3 docker.py unpack --manifest manifest.json --rootfs ./rootfs layer1.tar layer2.tar.gz

# Step 8 (config): inspect a manifest + config
python3 docker.py inspect --manifest manifest.json --config config.json

# Step 8 (config): run with the config's env + working directory
# (NOT isolated — see warning above)
python3 docker.py run-image --rootfs ./rootfs --config config.json
python3 docker.py run-image --rootfs ./rootfs --config config.json echo hi
```

Image references (`ubuntu`, `user/app:1.0`,
`registry.example.com:5000/ns/app@sha256:...`) are parsed by
`parse_image_ref` (default registry `docker.io`, `library/`
prefix, `:latest` default tag) for a future registry client;
no network call is made.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use temp directories only, need no root and no network,
and cover: run/exit codes, reference parsing, manifest/config
parsing, layer order/overwrite/whiteout/opaque handling, tar
safety (path traversal, escaping symlinks, setuid stripping),
and `run-image` env/workdir/entrypoint behaviour.

## Files

- `docker.py` — run, reference/manifest/config parsing, layer
  unpacking, config-driven runner, CLI.
- `docs/SPEC.md` — challenge steps, scoped subset, what is NOT built.
- `docs/DESIGN.md` — assumptions, components, divergences.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_docker.py` — the test suite.
