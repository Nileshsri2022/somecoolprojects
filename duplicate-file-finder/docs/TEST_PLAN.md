# Duplicate File Finder — TEST_PLAN

Suite: `tests/test_ccdupe.py`, Python `unittest`, run with:

```
python3 -m unittest discover -s tests -v
```

All fixtures are built in `tempfile.TemporaryDirectory` trees.
Tests never scan the user's real home directory or any fixed path.

## Fixture shape (mirrors Step Zero)

A helper builds a tree with: several random-content files of equal
size (100 bytes), a copied duplicate of one file, a duplicate placed
in a nested subdirectory, a same-size file with different content,
a unique-size file, and (where relevant) empty files. Each test builds
only the tree it needs, so failures localise to one behaviour.

## Coverage map

| Area | Tests |
| --- | --- |
| Step 1 `--list` | Recursive listing includes nested files, sorted, relative paths; empty directory lists nothing. |
| Step 2 `--potential` | Same-size files grouped; unique-size files excluded; group output format `Potential duplicates: ...`. |
| Step 3 `--probable` | Same-size different-content files excluded; true copies grouped; format `Probable duplicates: ...`. |
| Step 4 default | Confirmed duplicates reported; same-size different-content excluded; unique files excluded; multiple groups sorted; format `Duplicates: ...`. |
| MD5-collision safety | Monkeypatched `file_md5` returning a constant digest: files sharing a fake MD5 but differing in bytes are NOT reported as duplicates (byte compare saves them). |
| Step 5 `--minsize` | Files below the threshold excluded; a file exactly at the threshold included; `--minsize=1000` over a 100-byte tree prints nothing. |
| Step 6 `--delete` | Valid choice deletes exactly that file and prints `Deleted:`; invalid / empty / out-of-range input keeps all files; deletion of one group does not affect another; `--delete` with `--list`/`--potential`/`--probable` is a usage error (exit 2). |
| Symlinks | Symlink to a file skipped by default; symlinked directory not descended into by default; `--follow-symlinks` includes the target's content; a symlink loop with `--follow-symlinks` terminates. |
| Empty files | Two empty files reported as duplicates; `--minsize 1` excludes them. |
| Hardlinks | Two hardlinks to one inode reported as duplicates (documented: deleting one frees no space). |
| Unreadable / vanishing files | Unreadable file (chmod 0) skipped with a warning, scan still succeeds — skipped on platforms where chmod 0 does not block reads (e.g. running as root); a file deleted between walk and hash is skipped, not fatal. |
| CLI / errors | Missing directory → exit 2; file (not directory) as argument → exit 2; negative `--minsize` → exit 2; non-integer `--minsize` → exit 2; no directory argument → exit 2. |
| `--json` | JSON output parses to the same groups as the human output. |
| End-to-end (subprocess) | `python3 ccdupe.py <tmpdir>` finds a nested duplicate; `ccdupe.py --minsize=1000 <tmpdir>` prints nothing; piped delete choice deletes the chosen file. |

## How to run

```
cd duplicate-file-finder
python3 -m unittest discover -s tests -v
```

Expected result: every test passes, zero failures, zero errors.
Any skipped test must name its reason (platform/root-user caveat
above) in its skip message; skips are not silent passes.
