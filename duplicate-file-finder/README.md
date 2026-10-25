# Duplicate File Finder

A command-line tool that scans a directory recursively and finds files
with identical contents, so duplicates can be deleted to free storage
space. Built for the Coding Challenges challenge
[Build Your Own Duplicate File Finder](https://codingchallenges.fyi/challenges/challenge-duplicate-files/)
(tags: intermediate, algorithms, cli). Python 3 standard library only.

## Usage

```
python3 ccdupe.py [--list | --potential | --probable]
                  [--minsize N] [--follow-symlinks] [--json]
                  [--delete] <directory>
```

| Mode | Output |
| --- | --- |
| (default) | Confirmed duplicates: `Duplicates: file1 subdir/duplicateoffile1` |
| `--list` | Step 1: every file, recursively, one per line |
| `--potential` | Step 2: groups sharing a file size |
| `--probable` | Step 3: groups sharing an MD5 hash |
| `--minsize N` | Step 5: ignore files smaller than N bytes |
| `--delete` | Step 6: after printing each group, prompt for which file to delete |
| `--json` | Same groups as a JSON array (scripting extension) |
| `--follow-symlinks` | Follow symlinks (default: skipped) |

Paths are relative to the scanned directory, sorted within each
group, groups sorted by first path.

## How duplicates are confirmed

1. **Size** — files with a unique size cannot be duplicates and are
   never read.
2. **MD5** — files in a size group are hashed (streamed in 64 KiB
   chunks; MD5 is a fast fingerprint here, not a security mechanism).
3. **Byte-by-byte compare** — files sharing an MD5 are compared on
   every byte, so an MD5 collision can never produce a false positive.

## Deletion safety

Nothing is ever deleted unless `--delete` is passed. With it, each
group prompts:

```
Duplicates: file1 subdir/duplicateoffile1
Which file should be deleted?
  1) file1
  2) subdir/duplicateoffile1
  Any other value keeps the file and continues
```

A number deletes exactly that one file; anything else keeps all
files in the group and moves on.

## Limits (see `docs/SPEC.md` for the full list)

- Symlinks are skipped by default (`--follow-symlinks` opts in);
  directory symlink cycles are guarded either way.
- Hardlinked paths are reported as duplicates, but deleting one
  hardlink frees no space until every link is gone.
- All empty files are duplicates of each other; `--minsize 1`
  excludes them.
- No persistent hash cache: every run re-hashes, so results are
  never stale. No log file is written (redirect stdout instead),
  and there is no automatic all-but-one deletion.

## Tests

```
python3 -m unittest discover -s tests -v
```

Fixtures are built in temporary directories only; tests never scan
your real files. Full spec, design, and test plan are in `docs/`.
