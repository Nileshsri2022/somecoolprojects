# Tar — Design

## Assumptions (stated before coding)

1. Python 3 standard library only; single file `tar_tool.py`.
   The header logic is written by hand (struct-free byte
   slicing, octal encode/decode); `tarfile` is used ONLY in
   tests as an oracle, never in `tar_tool.py` itself.
2. Input paths are relative, as in the page's examples.
   Absolute paths and `..` components in archive entries
   are rejected on extract (see Security) rather than
   followed — GNU tar strips leading `/` instead; refusing
   is the safer, still page-compatible behaviour for the
   test fixtures, and is documented as a divergence.
3. Directory creation walks recursively, in sorted order,
   for deterministic archives. System tar uses directory
   order, so byte-for-byte `diff` against a system archive
   is NOT claimed (see README divergences); validity is
   claimed instead (system tar lists/extracts our output).
4. Metadata preserved: mode bits (permission + setuid/
   setgid/sticky, masked to 0o7777), uid, gid, mtime,
   uname, gname (best effort via `pwd`/`grp`; empty string
   and 0 when unavailable). Owner/group are NOT applied
   on extract as a non-root user would fail; modes and
   mtimes are applied.
5. Symlinks are stored, not followed, as typeflag `2` with
   the target in linkname, and recreated on extract.
   Hard links, devices, fifos are out of scope (see below).
6. Names are bytes-safe only as far as UTF-8/surrogateescape
   allows: names are encoded with `os.fsencode` so
   non-UTF-8 names round-trip on POSIX.

## Module layout (single file)

- `parse_octal(field)` / `format_octal(value, width)` —
  octal field codec; empty field decodes to 0.
- `compute_checksum(header)` — sum with chksum as spaces.
- `build_header(name, mode, uid, gid, size, mtime,
  typeflag, linkname, uname, gname)` — splits long names
  into prefix/name, fills magic/version, computes chksum.
- `parse_header(block)` — returns a `Header` (dataclass:
  name, mode, uid, gid, size, mtime, typeflag, linkname,
  uname, gname); verifies the checksum and raises
  `TarError` on mismatch; reconstructs prefix names.
- `iter_entries(stream)` — generator yielding
  `(Header, data_reader)` pairs; stops at two consecutive
  zero blocks or EOF; skips pax (`x`/`g`) and GNU longname
  (`L`/`K`) entries, applying a longname to the next entry.
- `cmd_list / cmd_extract / cmd_create` — one function
  per page step; `main(argv)` parses clustered flags.
- Archive I/O is streaming: data is copied in 512-byte
  blocks, never fully loaded, so large files work.

## Out of scope (nothing speculative)

- Compression (`.tar.gz`): the page lists it only under
  "Going Further". Not implemented.
- pax headers on write, hard links, devices, fifos,
  sparse files, incremental archives, `--format` selection.
- Byte-identical output to GNU tar (different blocking
  factor, padding, and header defaults make that a
  non-goal; see README).

## Security

- Extract rejects any entry whose normalised path is
  absolute or escapes the destination directory, and
  rejects symlinks whose target is absolute or escapes.
  A rejected entry aborts extraction with an error.
- Extract never follows a symlink already on disk as a
  parent directory component: parent dirs are created
  only if they do not already exist as symlinks.

## Success criteria (verifiable)

- `python3 -m unittest discover -s tests -v` passes.
- Round-trips: our archive extracts with system tar;
  system (ustar-format) archives list and extract with us.
- Contents are byte-identical after round-trip
  (checked with `diff` semantics in tests, not by eye).
