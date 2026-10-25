# cut — Design

## Assumptions (stated before coding, per ponytail)

1. Language: Python 3, standard library only, single file
   `ccut.py`, same as the previous projects in this repo.
2. Work on bytes, not text. Reason: `cut` is a byte/text
   pipeline tool; byte splitting avoids any decoding
   failure on non-UTF-8 input, and the delimiter (one
   character, UTF-8 encoded) splits byte streams correctly
   for ASCII delimiters and for multi-byte delimiters
   alike (a UTF-8 delimiter byte sequence cannot occur
   inside another character's encoding except as itself).
3. Stream line by line, do not read the whole file.
   Reason: `cut` is used in pipelines over large files;
   selection needs only one line at a time. This differs
   from `huffman.py`, which genuinely needs two passes.
4. Match GNU cut where it was checked, document where it
   differs. Checked on this machine before coding:
   out-of-order lists, duplicates, ranges, out-of-range
   fields, no-delimiter lines, empty fields, missing
   trailing newline, and the four error cases in SPEC.md.

## Field selection

The list is parsed into a set of selected field numbers
(1-based), plus a flag for "open-ended" ranges (`N-`):

```
parse_field_list("1,2")  -> {1, 2}, open_ended_from = None
parse_field_list("2-4")  -> {2, 3, 4}
parse_field_list("3-")   -> {}, open_ended_from = 3
parse_field_list("-2,5") -> {1, 2, 5}
parse_field_list("1 2")  -> {1, 2}   # single space splits too
```

Tokenising is done by hand, not by splitting on a
separator run, so that `1,,2`, `1, 2` and `1  2` are
rejected exactly as GNU cut rejects them (checked).

A set (not a list) is the right structure because GNU cut
outputs fields in line order with duplicates collapsed —
exactly set semantics, then filtered by line order.

For a line with fields `f[0..n-1]` (0-based):

```
if delimiter not in line:
    output line unchanged
else:
    selected = [f[i] for i in range(n)
                if (i + 1) in selected_set
                or (open_ended_from and i + 1 >= open_ended_from)]
    output delimiter.join(selected)   # possibly empty
```

Open-ended ranges: storing `open_ended_from = min` of all
`N-` items is enough, because any field >= the smallest
open start is selected by at least that range.

Validation happens before any input is read, so a bad
`-f` or `-d` fails fast with no partial output.

## CLI parsing

`argparse` with `-f` (required) and `-d` (default tab).
Attached forms (`-f1,2`, `-d,`) and separate forms
(`-f 1,2`, `-d ,`) both work. Positional files, zero or
more; `-` means stdin; zero files means stdin.

## File layout

```
cut/
  README.md            usage, examples, how to run tests
  ccut.py              field-list parsing, line cutting, CLI
  docs/
    SPEC.md            challenge spec and GNU-checked behaviour
    DESIGN.md          this file
    TEST_PLAN.md       what is tested, and against what
  tests/
    test_ccut.py       unittest, functions + CLI vs system cut
```

## Success criteria

- `python3 -m unittest discover -s tests -v` passes.
- Function and CLI outputs match system `cut` on the same
  fixtures for: single field, list, ranges, open ranges,
  out-of-order, duplicates, out-of-range, no-delimiter
  lines, empty fields, stdin, `-` filename, multi-file.
- Challenge step examples reproduced: `-f2` on a TSV,
  `-f1 -d,` on a CSV, `-f1,2` on both.
- Error cases exit non-zero: missing `-f`, field 0,
  decreasing range, multi-character delimiter, missing file.
