# cut — Specification (docs first)

Source: Coding Challenges, "Build Your Own cut Tool"
(https://codingchallenges.fyi/challenges/challenge-cut/)
Target in this repo: `somecoolprojects/cut/`

The Unix `cut` tool, rebuilt from its man-page behaviour
(checked against system GNU cut on this machine, not copied
from its source). One tool, one job: cut out selected
portions from each line of a file.

## Challenge steps

1. Open a tab-separated file, print the second field:
   `cut -f2 sample.tsv` gives `f1, 1, 6, 11, 16, 21, ...`.
2. `-d` sets the delimiter character. Default is tab.
   `cut -f1 -d, fourchords.csv` gives song titles.
3. `-f` takes a list of fields, comma- or whitespace-
   separated (`-f1,2` or `-f"1 2"`). The first field is
   field number 1. Output fields are separated by a single
   occurrence of the delimiter.
4. Read from stdin when no filename is given, or when the
   filename is a single dash `-`.
5. Pipeline use: `cut -f2 -d, fourchords.csv | uniq | wc -l`
   (155 unique artists in the challenge's data). This is a
   usage example, not extra code — it falls out of steps 1-4.

## Commands

```
ccut.py -f LIST [-d DELIM] [FILE ...]
ccut.py -f LIST [-d DELIM] -          # stdin
echo ... | ccut.py -f LIST [-d DELIM] # stdin
```

The file is named `ccut.py` (not `cut.py`) so it cannot
shadow the system `cut` or Python's own modules when run
from this directory.

## Field list syntax

- Items separated by a comma or a single space: `1,2` and
  `1 2` both mean fields 1 and 2 (challenge step 3).
  Checked against GNU cut: `1,,2`, `1, 2` and `1  2`
  (double space) are all rejected by GNU cut, and are
  rejected here too — a separator is exactly one comma
  or one space, not a run of them.
- Each item is one of:
  - `N` — field N only
  - `N-M` — fields N through M inclusive
  - `N-` — field N through the last field on the line
  - `-M` — field 1 through M
- Fields are numbered from 1. `0` is an error.
- A decreasing range (`2-1`) is an error.
- A non-numeric item, an empty item (`1,,2`), or a missing
  `-f` value is an error.

These range forms are not spelled out in the challenge
text, which only says "a list of fields", but they are
part of real `cut` (man page) and are needed to be a
faithful clone, so they are included and tested against
system cut.

## Line processing (verified against GNU cut)

- Split each line on the delimiter byte. Empty fields are
  real fields: `a,,c` with `-d,` has fields `a`, ``, `c`.
- Selected fields are output in the order they appear in
  the line, not the order they were listed, and duplicates
  are collapsed: `-f3,1` on `a b c d` gives `a c`;
  `-f2,2` gives `b`.
- Output fields are joined by a single delimiter.
- A line that does not contain the delimiter is output
  whole and unchanged, whatever `-f` says. (Exception:
  this is the line, not the field: a line with a delimiter
  but no selected fields present gives an empty line.)
- Every output line ends with `\n`, even if the input's
  last line did not. Verified: GNU cut adds it.
- A line with a trailing `\r` (CRLF input) keeps the `\r`
  as part of its last field, as GNU cut does. No CRLF
  special-casing.

## Delimiter

- Default: tab.
- `-d` must be exactly one character. A multi-character
  argument is an error, as in GNU cut. Note: the shell
  must pass a real tab for `-d` tab, e.g. `$'\t'`; the
  two characters `\` + `t` are not interpreted as a tab.
- The delimiter is encoded as UTF-8 and lines are split
  on those bytes, so non-ASCII single-character delimiters
  work as well as ASCII ones.

## Errors

- Missing `-f`: error, exit non-zero.
- Bad field list / bad delimiter: error message on
  stderr, exit non-zero, no output.
- Missing/unreadable file: message on stderr, other files
  are still processed, exit code 1 at the end (GNU style).

## Out of scope (ponytail: smallest change that solves it)

- No `-b` (bytes) or `-c` (characters) modes. The
  challenge is the field mode only.
- No `--complement`, no `-s` (suppress lines without
  delimiter), no `--output-delimiter`. The challenge
  never asks for them; output delimiter is always the
  input delimiter.
- No `--zero-terminated` or other GNU extensions.
