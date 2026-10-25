# xxd — Test Plan

Run from `~/workspace/somecoolprojects/xxd/`:

```sh
python3 -m unittest discover -s tests -v
```

Tests use `tempfile` only — no fixture files in the repo, no writes
outside the temp directory, no network, no system `xxd` (which is
not installed here anyway).

## Coverage map

Library level (`format_line`, `dump`, `revert` on in-memory streams):

- Default dump: page Step 1 first line, verbatim
  (`file1.txt` + NULs -> `00000000: 6669 6c65 ...  file1.txt.......`).
- `-e` and `-e -g 8`: page Step 2 first lines (with the documented
  2-space separator — see README divergences).
- `-c 4` with `-l 16`: all four page Step 3 lines, verbatim.
- `-s` seek: page Step 4 pattern — bytes at offset 512 dump with
  offset `00000200`, and a Step 4-style `-s 124 -l 12` case.
- Group sizes: `-g 1` (single bytes), `-g 4`, group larger than
  columns (single group per line), partial final group.
- Short final line: ASCII column aligned by hex-field padding.
- Non-printable bytes render as `.`; DEL (0x7f) and 0x80+ render
  as `.`; space (0x20) and `~` (0x7e) render as themselves.
- Empty input -> empty output; `-l 0` -> empty output; seek past
  EOF -> empty output; negative `-s` counts back from EOF.
- `-l` truncates mid-line and across lines.

Reverse mode:

- Round-trip: dump then revert restores the original for text,
  binary (all 256 byte values), and empty input, normal and `-e`.
- Revert of the page's own Step 1-style dump lines (offset +
  ASCII column) restores the bytes.
- ASCII column ignored even when it looks like hex (input whose
  text is `dead`).
- Plain hex with no offsets reverts; blank lines skipped; uppercase
  hex accepted; odd-length hex token and non-hex token are errors.
- `-l` limits restored bytes; `-s` positions output (NUL gap on a
  stream).

CLI level (subprocess, temp files only):

- File in/out, stdin in, output-file argument.
- Invalid `-g` (3, 0), invalid `-c` (0), malformed `-s`: non-zero
  exit with a stderr message.
- Missing input file: non-zero exit.
- Page tarball scenario end-to-end: build a tarball in a temp dir,
  dump it, check the first line matches the page's Step 1 line.

## What is NOT tested

- Byte-for-byte comparison against system `xxd`: impossible here,
  it is not installed. If run where `xxd` exists, compare with:
  `xxd <file> | diff - <(python3 xxd.py <file>)` for the default
  mode and the `-e`/`-c`/`-l`/`-s` variants; the known `-e`
  spacing question (README) is the first thing to check.
