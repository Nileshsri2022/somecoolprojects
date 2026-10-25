# xxd — Specification

Source: Coding Challenges, "Build Your Own Xxd".
Page slug used: `challenge-xxd`
URL: https://codingchallenges.fyi/challenges/challenge-xxd/
(First-guess slug worked; no 404, no correction needed.)

## Steps implemented (page Steps 0–5)

- Step 1 — Default hex dump. Each line has three sections: the offset
  into the file (8 lowercase hex digits, zero-padded, widening past
  `ffffffff`), a colon, a space, the data as hex, two spaces, and the
  data as text (printable ASCII 0x20–0x7e as-is, every other byte `.`).
  16 bytes per line by default. Hex bytes are grouped in pairs
  (group size 2): groups are joined by a single space.
- Step 2 — Little-endian mode (`-e`). Bytes inside each group are
  printed in reverse order (the group is treated as a little-endian
  word). Default group size in `-e` mode is 4; `-g` overrides it.
  Invalid `-g` values are rejected with an error (see DESIGN.md).
- Step 3 — `-l` (number of octets to dump) and `-c` (columns, i.e.
  bytes per line).
- Step 4 — `-s` (seek to a byte offset before dumping).
- Step 5 — Reverse mode (`-r`): convert a hex dump back to binary.

## Command line

```
python3 xxd.py [-e] [-g GROUP] [-c COLS] [-l LENGTH] [-s OFFSET]
               [-r] [infile [outfile]]
```

- No `infile` means read stdin (binary). A second positional argument
  is the output file; otherwise output goes to stdout (binary for
  `-r`, text for a dump).
- `-s` accepts decimal or `0x`-prefixed hex. A negative `-s` seeks
  that many bytes before end-of-file (forward dump only; for stdin it
  is applied after reading, see DESIGN.md). Seeking past end-of-file
  produces no output, not an error.
- `-r` also accepts `-s` (seek in the output; on stdout the gap is
  filled with NUL bytes) and `-l` (limit on restored bytes). `-c` is
  ignored in reverse mode: lines are parsed as written, whatever their
  width. `-r -e` reverses the byte order inside each group again, so
  a dump made with `-e` round-trips (group size from `-g`, default 4
  in `-e` mode).

## Reverse-mode input format

Each line may be:

- `00000000: 6669 6c65  ...  file1.txt.......` — offset, hex field,
  ASCII column (the page's own dump format), or
- plain hex with no offset and no ASCII column, e.g. `66696c65`.

Parsing rule: an optional leading `hexdigits:` offset is stripped;
the remainder is split on runs of two or more spaces, and only the
first segment is read as hex. Everything after that (the ASCII
column) is ignored — even if it happens to look like hex (e.g. a file
whose text is `dead`). Hex tokens must be even-length strings of hex
digits; anything else in the hex segment is an error. Blank lines are
skipped. Offsets in the input are ignored (output order is input
order); use `-s` to position the output explicitly.

## Errors

- Missing/unreadable input file, unwritable output file: message on
  stderr, exit code 1.
- Invalid option values (`-g` not a power of two in 1..256, `-c`
  outside 1..256, `-l` negative, malformed `-s`, odd/invalid hex in
  reverse mode): message on stderr, exit code 1 (unknown flags exit 2
  via the argument parser, as usual).
- An empty input dumps to empty output (no header line).

## Out of scope (not on the page)

`-p` (plain hex), `-u` (uppercase), `-b` (bits), `-o` (display
offset), `-v`, `-a` (autoskip `*` lines), and the `xxd -r` "seek to
offset embedded in the dump" behaviour are not implemented. Nothing
speculative was added beyond the `-r -e` round-trip noted above.
