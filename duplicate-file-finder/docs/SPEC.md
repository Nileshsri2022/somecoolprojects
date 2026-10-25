# Duplicate File Finder — SPEC

Source challenge: **Build Your Own Duplicate File Finder**,
Coding Challenges (codingchallenges.fyi).

Resolved challenge URL (verified by reading the page in full, 2026-10-25):
https://codingchallenges.fyi/challenges/challenge-duplicate-files/

Tags on codingchallenges.fyi: intermediate, algorithms, cli.
The page's own binary is named `ccdupe`; this project ships that behaviour
as `ccdupe.py` (Python 3 standard library only).

## What the tool does

A command-line tool that scans a directory recursively, identifies files
with identical contents, and — only when the user explicitly asks — helps
delete the duplicates to free storage space.

## Challenge steps (as specified on the page)

### Step Zero — test data

Set up the language/tooling of choice, then create test data, e.g.
20 random 100-byte files plus a copy of one of them, with duplicates in
subdirectories at different levels of the hierarchy.

*Built:* the test suite builds exactly this shape of fixture tree in
temporary directories (random-content files of equal size, a copied
duplicate, duplicates nested in subdirectories). No real user directory
is ever scanned by the tests.

### Step 1 — recursive listing

Accept a directory on the command line and list all files in it
recursively, e.g.:

```
% ccdupe .
file1
file2
subdir/file11
subdir/anothersubdir/file21
```

*Built:* `ccdupe.py --list <dir>` prints one relative path per file,
sorted, one per line.

### Step 2 — size grouping ("potential duplicates")

Record each file's size; files sharing a size are reported as potential
duplicates, and the plain listing is removed from the default output:

```
% ccdupe .
Potential duplicates: file1 file2
# ... snipped duplicates of file1 to file 20.
Potential duplicates: file1 subdir/duplicateoffile1
```

*Built:* `ccdupe.py --potential <dir>` prints one
`Potential duplicates: <paths...>` line per size group with 2+ files.
Size alone is only a filter — files of equal size with different
contents are never reported as real duplicates by the default mode.

### Step 3 — MD5 hashing ("probable duplicates")

Calculate an MD5 hash for each file and compare it with previously seen
hashes. Files with a matching MD5 are probable duplicates:

```
% ccdupe .
Probable duplicates: file1 subdir/duplicateoffile1
```

The page suggests MD5 (not SHA1/SHA256) because it is faster and the
hash is not used cryptographically, and notes a full check can reduce
the chance of a false match further. It also floats storing hashes in
SQLite to cache results between runs, with a warning about checking
cached values are still correct.

*Built:* MD5 is computed by streaming each file in 64 KiB chunks, but
only for files whose size group has 2+ members (size filtering first,
so unique-size files are never hashed). `ccdupe.py --probable <dir>`
prints one `Probable duplicates: <paths...>` line per MD5 group.
*Not built:* the SQLite cache. Caching hashes across runs is listed
on the page only as an option ("you could"), and a stale cache can
report files that have changed as duplicates. This build hashes fresh
on every run, in memory only, so results are never stale. See
"Deliberate divergences".

### Step 4 — full byte-by-byte confirmation ("duplicates")

Check that probable duplicates really are duplicates by comparing
every byte of each file with the same byte in the other file, then
report:

```
% ccdupe .
Duplicates: file1 subdir/duplicateoffile1
```

*Built:* this is the default mode. Within each MD5 group, files are
compared byte-by-byte in chunks against the group's first file; only
files that match on every byte are reported. The default output is
one `Duplicates: <paths...>` line per confirmed group, paths sorted,
groups sorted by their first path. (A byte-by-byte compare after an
MD5 match is, in practice, a re-read; it is kept because the page
specifies it and it eliminates any MD5-collision false positive.)

### Step 5 — minimum size filter

Take an optional argument defining the minimum file size to consider:

```
% ccdupe --minsize=1000 .
%
```

*Built:* `--minsize N` (also `--minsize=N`) skips files smaller than
N bytes. The example above prints nothing when every file is below
1000 bytes. N must be a non-negative integer; anything else, and a
missing directory, exit with code 2 and a usage error on stderr.

### Step 6 — delete duplicates, interactively

Prompt the user to select which file to delete, per duplicate group:

```
% ccdupe .
Duplicates: file1 subdir/duplicateoffile1
Which file should be deleted?
  1) file1
  2) subdir/duplicateoffile1
  Any other value keeps the file and continues
```

*Built:* `--delete` turns on this prompt, once per duplicate group,
after the group is printed. Entering a number deletes exactly that
one file; any other input (including an empty line or EOF) keeps all
files in the group and moves on. Deletion is strictly opt-in: without
`--delete` nothing is ever deleted. Deleted paths are reported on
stdout as `Deleted: <path>`; a failed delete is reported on stderr
and does not abort the remaining groups.

### Going Further (page's ideas)

- Handle symlinks.
- Delete duplicates.
- Write to a log.

*Built:* delete duplicates (Step 6, above); symlink handling (below).
*Not built:* writing a scan/delete log to a file. `--delete` already
prints `Deleted: <path>` lines to stdout, which the user can redirect
to a log file (`ccdupe.py --delete . > dupes.log`); no separate log
file option was added to keep the interface to what the page specifies.

## Command-line interface (as built)

```
ccdupe.py [--list | --potential | --probable] [--minsize N]
          [--follow-symlinks] [--json] [--delete] <directory>
```

| Flag | Effect |
| --- | --- |
| (none) | Default: print confirmed duplicate groups (`Duplicates: ...`). |
| `--list` | Step 1: list all files recursively, one per line. |
| `--potential` | Step 2: size-only groups. |
| `--probable` | Step 3: MD5-only groups (no byte compare). |
| `--minsize N` / `--minsize=N` | Step 5: ignore files smaller than N bytes. |
| `--follow-symlinks` | Follow symlinked directories and hash symlinked files (see below). |
| `--json` | Machine-readable output: a JSON array of groups (each group a list of relative paths). Extension, not on the page; see below. |
| `--delete` | Step 6: interactive per-group delete prompt. Only valid with the default (confirmed-duplicates) mode. |

Paths in output are relative to the scanned directory, using `/`
separators, sorted within each group. Groups are sorted by their
first path. Exit codes: 0 = scan completed (even if no duplicates
were found, or some files were unreadable — those are warned about
on stderr); 2 = usage error (bad flag, bad `--minsize`, missing or
non-directory argument, or `--delete` combined with a non-default
mode).

## Hashing strategy

1. Group by file size. Files with a unique size cannot be duplicates
   and are never read.
2. Within each size group of 2+, compute MD5, streaming in 64 KiB
   chunks so large files are never loaded whole into memory.
   (`hashlib.md5(usedforsecurity=False)` where the platform supports
   it; plain `hashlib.md5()` otherwise. MD5 is used only as a
   fast content fingerprint, never for security, exactly as the
   page prescribes.)
3. Within each MD5 group of 2+, confirm byte-by-byte against the
   group's first file, again in 64 KiB chunks, so an MD5 collision
   can never produce a false duplicate.

## Symlinks, hardlinks, empty files, and other limits

- **Symlinks:** by default symlinks are NOT followed. A symlink to a
  file is skipped (it is not a separate copy, and deleting it would
  not free the target's space); a symlinked directory is not
  descended into (avoids cycles). With `--follow-symlinks`, symlinks
  are followed and their targets are treated as ordinary files, and
  directory cycles are still guarded by tracking visited
  (device, inode) pairs for directories. A broken symlink is skipped
  with a stderr warning in both modes.
- **Hardlinks:** two paths to the same inode are byte-identical, so
  they are reported as duplicates like any other identical files.
  Deleting one hardlink does NOT free disk space (the data remains
  until every link is gone) — the delete prompt does not special-case
  this; the user should be aware before deleting hardlinked paths.
- **Empty files:** all empty files have the same size (0) and the
  same MD5, so they are reported as duplicates of each other.
  `--minsize 1` excludes them, which is the intended way to ignore
  them when freeing space is the goal.
- **Unreadable files:** a file that cannot be opened (permissions,
  disappearing mid-scan) is skipped with a warning on stderr; the
  scan continues and still exits 0.
- **Hidden files and dot-directories:** scanned like any other file;
  there is no exclusion list.
- **No recursion into the same directory twice:** directory cycles
  via symlinks are guarded (see above); plain directory trees are
  walked once.
- **No cross-run cache:** see Step 3 divergence — every run re-hashes.
- **No content-aware deduplication:** only whole-file duplicates are
  found. The page's note about enterprise backups finding duplicates
  *within* files (chunk-level dedup) is background context, not a
  specified step, and is not built.
- **Output paths are relative:** absolute paths are never printed;
  the scanned directory itself is the reference point.

## Deliberate divergences

1. **No SQLite hash cache (Step 3 option, not a requirement).**
   The page says "you could" cache in SQLite and warns cached values
   must be revalidated. This build re-hashes every run instead, so
   results can never be stale. No `--cache` flag exists.
2. **Mode flags instead of separate programs per step.**
   Steps 1–4 are successive versions of one program on the page; this
   build keeps them all behind `--list` / `--potential` /
   `--probable` / default, so each step's behaviour stays testable
   without losing the later steps.
3. **`--json` output added.** Not on the page. It emits the same
   groups as a JSON array for scripting (e.g. feeding a backup
   exclusion list, the page's other stated use). It does not change
   the default human-readable output.
4. **`--delete` restricted to the default mode.** The page's delete
   prompt follows confirmed duplicates; prompting over merely
   "potential" or "probable" groups could delete non-identical files,
   so `--delete` with `--list`/`--potential`/`--probable` is a
   usage error (exit 2) rather than a silent reinterpretation.
5. **Symlink default is "do not follow".** The page lists "handle
   symlinks" only as a Going Further idea without a specified
   default; skipping them by default is the safe choice (deleting a
   symlink frees nothing, following directory symlinks can loop),
   with `--follow-symlinks` as the explicit opt-in.
6. **Binary name.** The page's `ccdupe` is invoked here as
   `python3 ccdupe.py`; no installed wrapper script is shipped.

## Anything NOT built (honest list)

- SQLite / persistent hash cache between runs.
- Writing a scan/delete log to a file (stdout `Deleted:` lines can
  be redirected instead).
- Chunk-level / within-file deduplication (enterprise-backup style).
- A GUI, a daemon/watch mode, or automatic (unprompted) deletion.
- Deleting all-but-one automatically without prompting — every
  deletion goes through the Step 6 prompt when `--delete` is used.
