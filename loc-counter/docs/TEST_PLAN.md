# loc-counter — TEST_PLAN

All tests use `unittest` and `tempfile.TemporaryDirectory`
fixtures with hand-computed counts. The somecoolprojects
tree itself is never used as a fixture (that would be
circular: the tool counting its own source proves nothing
about known counts).

## Library tests (`tests/test_loc.py`)

Python file:
- blank lines, `#` full-line comments, code lines,
  trailing comment after code (counts as code),
  `#` inside a double-quoted string (counts as code,
  not a comment). Known totals asserted exactly.

C-like file, Step 3:
- `//` full-line and trailing comments, multi-line
  `/* ... */` block, single-line `/* ... */` block
  (comment), single-line block with code after it (code).

C-like file, Step 4 (the page's example, generalised):
- `int x = 0; /* start` / ` middle` / ` end */` /
  `int y = 1;` -> lines 4, blanks 0, comments 2, code 2.

Markdown file (Step 5):
- prose, blank lines, fenced block with info string,
  fence delimiters -> exact blank/code counts, comments 0.

Text file (Step 5):
- blank vs non-blank only, comments 0.

Directory walk:
- recursive walk finds files in subdirectories, groups
  them per language, skips unknown extensions and hidden
  files/directories, and totals equal the sum of the
  per-file counts; every file satisfies
  `lines == blanks + comments + code`.
- empty directory -> zero files, zero totals.
- binary file (NUL byte) skipped; file without a trailing
  newline still counts its last line.

## CLI tests (same file, subprocess-free via `main()`)

- Default run on a fixture tree prints a per-language
  table containing the language name and the total row.
- `--files` prints relative paths and per-file counts.
- `--json` prints parseable JSON whose `files`,
  `languages`, and `total` agree with the library counts.
- Missing path exits non-zero with a message on stderr;
  an empty argument list exits non-zero (usage error).
