# Duplicate File Finder — DESIGN

## Overview

One file, `ccdupe.py`, Python 3 standard library only
(`argparse`, `hashlib`, `json`, `os`, `sys`). No third-party
dependencies, no threads, no database. The pipeline is a chain of
cheap-to-expensive filters so large trees are scanned without reading
every file's contents:

```
walk tree → size groups → MD5 groups → byte-compare groups
   (free)      (stat)        (read)         (re-read)
```

Only files that survive each filter are read by the next stage.

## Module layout

`ccdupe.py` (single file, functions kept importable for tests):

| Function | Responsibility |
| --- | --- |
| `parse_args(argv)` | `argparse` CLI; validates `--minsize >= 0` and that `--delete` is only combined with the default mode. |
| `collect_files(root, follow_symlinks)` | Recursive walk returning sorted relative paths of regular files. Skips symlinks unless following them; guards directory cycles via visited `(st_dev, st_ino)` pairs when following symlinks; warns on stderr for broken symlinks and unreadable directories. |
| `group_by_size(root, files, min_size)` | `stat` each file, drop files below `min_size`, group the rest by size, keep groups of 2+. Unreadable/vanishing files are warned about and skipped. |
| `file_md5(path)` | Stream a file in 64 KiB chunks through MD5. Returns `None` on read error (caller warns and skips). |
| `group_by_md5(root, size_groups)` | MD5 each file in each size group; keep MD5 groups of 2+. |
| `files_identical(path_a, path_b)` | Chunk-wise byte comparison; short-circuits on the first differing chunk and on size mismatch. |
| `confirm_duplicates(root, md5_groups)` | Within each MD5 group, compare every file byte-by-byte against the group's first file; keep confirmed groups of 2+. (Files differing from the first file despite sharing an MD5 — i.e. a collision — would form their own check against the first file and be dropped; in practice this never happens, but the logic does not assume it can't.) |
| `find_duplicates(root, ...)` | Orchestrates the pipeline; returns confirmed groups (sorted paths, sorted groups). |
| `find_potential / find_probable` | Thin wrappers exposing the Step 2 / Step 3 stages. |
| `prompt_delete(groups, input_fn, ...)` | Step 6 prompt loop: prints each group, asks which file to delete, deletes exactly the chosen one on a valid number, keeps everything otherwise. `input_fn` is injectable so tests can drive it without a tty. |
| `main(argv)` | Wires CLI → pipeline → output (human or `--json`) → optional delete pass. Returns the exit code. |

## Key decisions

- **Size before hash before bytes.** `stat` is far cheaper than
  reading, and hashing is far cheaper than a pairwise byte compare
  of everything. This is exactly the page's progression (Steps 2→4)
  and it means a tree of all-unique-size files is scanned without
  opening a single file.
- **MD5, not SHA-256.** The page prescribes MD5 for speed since the
  hash is not a security mechanism, and the Step 4 byte compare
  removes any collision risk. `usedforsecurity=False` is passed
  where supported (FIPS-mode OpenSSL builds reject plain MD5
  otherwise); a `TypeError` fallback keeps older Pythons working.
- **Streaming everywhere.** Both hashing and byte comparison read
  in 64 KiB chunks, so a multi-gigabyte file never lands whole in
  memory. Only path strings and small digests are held.
- **Sorted, deterministic output.** Files are collected sorted,
  paths within a group are sorted, groups are sorted by first path.
  The same tree always produces the same output, which is what
  makes the output diffable and the tests stable.
- **Relative paths.** Output paths are relative to the scanned root
  (computed with `os.path.relpath`), so output is portable and never
  leaks absolute locations.
- **Deletion is a separate, explicit pass.** The scan completes and
  prints first; only then, and only with `--delete`, does the prompt
  loop run. Nothing is deleted as a side effect of scanning, and a
  group is never auto-pruned to one survivor.
- **Errors warn, they don't abort.** A file that vanishes or can't
  be read mid-scan produces one stderr warning and is skipped; the
  scan still exits 0. Genuine usage errors (bad directory, bad flag,
  bad `--minsize`) exit 2 before any scanning.

## Data flow (default mode)

```
root
  └─ collect_files → [relpath, ...]           (sorted)
       └─ group_by_size → {size: [paths]}     (groups of 2+, ≥ minsize)
            └─ group_by_md5 → {md5: [paths]}  (groups of 2+)
                 └─ confirm_duplicates → [[paths], ...]  (byte-confirmed)
                      └─ print "Duplicates: ..." / JSON
                           └─ if --delete: prompt_delete per group
```

## Edge cases handled

- Empty directory / no duplicates → no output, exit 0.
- All files unique size → no output without reading any file.
- Same size, different content → excluded at the MD5 stage.
- Same MD5, different content (collision) → excluded at the byte
  stage (covered by a test that monkeypatches the hash).
- Symlink loop (`dir/link -> ..`) with `--follow-symlinks` →
  visited-inode guard stops the cycle.
- Broken symlink → warning, skipped, scan continues.
- File deleted between walk and hash → warning, skipped.
- `--minsize` boundary: a file exactly `minsize` bytes is included
  (filter is "smaller than", matching "below a certain size").
- Delete prompt input: out-of-range number, non-numeric input,
  empty line, EOF → keep everything, continue to next group.
