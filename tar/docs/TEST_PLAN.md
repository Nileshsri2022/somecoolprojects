# Tar — Test Plan

Run from `~/workspace/somecoolprojects/tar/`:

```sh
python3 -m unittest discover -s tests -v
```

All tests use `tempfile.TemporaryDirectory` only — no
files are created in the repo, and no test touches the
system tar's working directory outside a temp dir.

## Cases (`tests/test_tar_tool.py`)

Header unit tests (no filesystem, no system tar):

1. Header round-trip: build then parse preserves name,
   mode, uid, gid, size, mtime, typeflag, linkname.
2. Checksum: stored checksum equals the space-field sum;
   flipping one header byte is detected as `TarError`.
3. Long name: a 120-byte path splits into prefix/name
   and parses back to the full name.
4. Name too long for prefix split (no `/`, or prefix >
   155) raises `TarError` on create.

CLI tests (subprocess, `tar_tool.py` as a script):

5. Step 1 list: archive built by system tar
   (`tar --format=ustar -cf`) lists the page's three
   files, in order, from `-tf` and from stdin (`-t`).
6. Step 1 verbose: `-tvf` output contains mode, size
   and name for each entry.
7. Step 2 extract: system archive extracts with identical
   bytes and preserved mode.
8. Step 3 create: our archive is listed and extracted by
   system tar with identical bytes; `tarfile` (oracle
   only) lists the same names.
9. Full round-trip (ours only): create -> list -> extract
   preserves bytes for empty file, 1-byte file, exactly
   512 bytes, 513 bytes, and binary data.
10. Directories: nested dirs and an empty dir survive a
    round-trip; directory entries end with `/` in listings.
11. Symlink: a symlink round-trips as a symlink with the
    same target (system tar agrees).
12. End-of-archive: our archive ends with two zero blocks
    and its total size is a multiple of 512.
13. Errors: missing archive file, corrupt checksum, and
    truncated archive all exit non-zero with a message.
14. Traversal: an archive containing `../evil.txt`
    (hand-built header) is refused on extract and writes
    nothing outside the destination.
15. Missing input on create exits non-zero.

## Oracle policy

- System `tar` is used as an interoperability oracle
  (tests skip the system-tar cases if `tar` is absent,
  via `shutil.which`).
- `tarfile` is used only as a second oracle for listing
  our archives; it is never imported by `tar_tool.py`.
