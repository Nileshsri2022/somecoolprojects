# sed — DESIGN

## Assumptions (stated before coding, ponytail rule)

1. The page gives no step-by-step test list beyond Steps 0–6, so the
   parent task's list (substitute with flags, print, delete, `-n`,
   address ranges, stdin/files) plus the page's `G` and `-i` is the
   contract. Anything beyond that is out of scope (see SPEC).
2. Easy difficulty: Python `re`, not a hand-written regex engine.
   The page explicitly offers this option.
3. Input is text. Decoding is UTF-8 with `surrogateescape` so that
   non-UTF-8 bytes round-trip byte-for-byte instead of crashing;
   output re-encodes the same way. This keeps the "compare against
   system sed" tests meaningful on arbitrary fixtures.
4. One file, `ssed.py`, stdlib only. The module name avoids
   shadowing the system `sed` binary (there is no `sed.py` stdlib
   module to clash with, but `ssed` also matches the repo's
   `ccut`/`ssort`-style naming).
5. Line numbers reset per file and `$` means last line of the
   current file. This matches GNU sed's default (no `-s` flag is
   offered, so there is no ambiguity to resolve).
6. `;` separates commands, but a `;` inside an `s` command must not
   split it. Rather than a full sed parser, the splitter scans a
   script line char by char, tracking whether it is inside an `s`
   command's fields (delimiter-aware, backslash-aware) and only
   splits on `;` outside those fields. Newlines in a script also
   separate commands. This is the smallest parser that covers
   `sed -e 's/a/b/;p'` correctly.

## Architecture

```
main(argv)
  parse_args()          # -n, -i[SUFFIX], -e, -f, --, script, files
  parse_script(text)    # -> list[Command]; raises SedError
  for each input (file or stdin):
      if -i and a real file: collect output lines, then rewrite file
      else: stream lines to stdout
  process_stream(lines, commands, opts)   # the cycle, per file
```

- `Command` is a small class: `addr1`, `addr2` (Address or None),
  `kind` (`s`/`p`/`d`/`G`/`q`), plus `s`-specific fields
  (compiled pattern, replacement, flags, w-file handle).
- `Address` is (`kind`, `value`): `line` (int), `last`, or `regex`
  (compiled pattern). A range's state lives in the cycle, not in
  the command: `range_active` per command, reset at each file.
  The cycle, per line, per command, in order:
  1. If the command has an address and it does not match this line,
     skip it (but a range that is already active still matches).
  2. `d` aborts the rest of the cycle for this line.
  3. `q` sets a quit flag; the cycle finishes this line's automatic
     print, then processing stops entirely.
  4. After all commands, print the pattern space unless `-n` or
     the line was deleted. Prints are collected as
     (pattern, source-terminator) chunks and rendered once per
     destination by `render()` — see its docstring for the
     final-newline rule verified against GNU sed.
- Range bookkeeping: when a non-active range's start address
  matches, the range becomes active. The end address is then
  checked: for a line-number end, the range ends on this same line
  if `line_no >= end`; for a regex end, the check starts on the
  next line (a regex end matching the start line itself must not
  close a one-line range — verified against GNU sed behaviour for
  `/a/,/b/` on a line containing both). `$` as an end address
  closes the range on the last line. If the end is a line number
  smaller than the start, the `>=` check closes it on the start
  line, matching GNU sed.
- Substitution: `re.sub` with a callback so `&` and `\1`–`\9`
  expand per match without `re`'s own replacement syntax getting
  in the way. For a numeric flag, only the Nth match is replaced
  (counted per line); for `g`, all; otherwise the first.
  The "last regex" for an empty pattern is the most recently
  compiled pattern or address regex, shared across the script
  (GNU sed semantics, simplified to script order).
- `w` files: opened (truncated) once at parse time, appended to
  during processing, closed at the end of `main`. With `-i` the
  `w` output still goes to the `w` file, not into the edited file.
- In-place editing: output for a file is collected in memory and
  written back only after the whole file was read successfully.
  (Streaming to a temp file would be more memory-frugal, but the
  in-memory form is ~15 lines simpler and files in this challenge
  are small; a multi-GB file is not a stated success criterion.)
  The backup, when requested, is a byte copy of the original made
  before overwriting. File permissions of the original are
  preserved by writing through the same path with `open(path, 'w')`
  semantics... actually `open(path, 'wb')` truncates in place, which
  preserves inode, owner and mode — deliberately chosen over
  write-to-temp-and-rename for that reason.

## Success criteria (verifiable)

- Every test in `tests/test_ssed.py` passes (see TEST_PLAN.md).
- The page's Step 1–6 examples reproduce on the fixture quotes file.
- Byte-for-byte equality with GNU sed 4.9 on the overlapping
  behaviour covered by the comparison tests (all tests marked
  "vs system sed").
