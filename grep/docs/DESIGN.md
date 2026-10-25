# DESIGN — grep.py

## Assumptions (stated before coding)

- Easy path: Python's `re` module, not a hand-written engine.
- Only the page's options: `-r`, `-v`, `-i`. No other flags.
- Byte-based matching (see SPEC.md): avoids encoding errors on
  arbitrary files and makes `\d`/`\w` ASCII-only, matching GNU grep
  in the C locale.
- One pass, streaming: lines are read and printed one at a time, so
  arbitrarily large files need only one line in memory.
- Deterministic recursion: sorted directory entries (SPEC.md notes
  this diverges from GNU readdir order).

## Structure (single file, `grep.py`, stdlib only)

- `parse_args(argv)` — hand-rolled, no `argparse` (argparse's
  exit code is 2, but its usage text and its handling of `-` and
  bundled flags would fight the GNU-like behaviour; a ~30 line
  parser is simpler and exact). Returns `(pattern, files, recursive,
  invert, ignore_case)` or raises `UsageError`.
  - A leading `-` argument that is not exactly `-` and not after
    `--` is an option bundle; each character must be `r`, `v`, or
    `i`, else `UsageError`.
  - The first non-option argument is the pattern; the rest are files.
  - No pattern at all → `UsageError`.
- `compile_pattern(pattern, ignore_case)` — `os.fsencode` the pattern
  (so a non-ASCII pattern survives the shell's encoding), then
  `re.compile` with `re.IGNORECASE` when `-i`. `re.error` becomes a
  user-facing error, exit 2.
- `iter_inputs(files, recursive)` — yields `(display_name, stream)`
  pairs:
  - No files → one stdin input, display name `None` (no prefix),
    except with `-r`, which recurses `.` with `./` stripped from
    display names.
  - `-` → stdin, display name `(standard input)`.
  - A directory with `-r` → walk it with `os.walk`, entries sorted,
    yielding each file; a directory without `-r` → error.
  - Anything else → open in `rb`; `OSError` → error, keep going.
  - Prefixing rule: prefix when more than one file operand was
    given (a missing file still counts as an operand), or when a
    directory was recursed (GNU prefixes a recursed directory's
    matches even if it yields one file; a single file operand with
    `-r` gets no prefix).
- `search_stream(stream, regex, invert, prefix, out)` — for each line
  (split keeping the newline): `matched = regex.search(line)` with
  the trailing newline stripped for matching only (a pattern such
  as `$` must match at the end of the content, not after the
  newline — Python `$` on bytes already matches before a trailing
  newline, but stripping keeps it exact and also handles `\r\n`
  input the same way GNU grep does for `$`... note: only `\n` is
  stripped, `\r` is content). Invert with `-v`. Write the line,
  appending `\n` if the original lacked one. Returns whether any
  line matched.
- `main(argv)` — wires the above together, counts matches and
  errors, writes errors to stderr as `grep.py: <detail>`, returns
  2 if any error, else 0 if any match, else 1.

## Why not argparse / text mode

- `argparse` prints its own usage and exits 2 on error, but it also
  treats `-` oddly with nargs and would need `parse_known_args`
  workarounds for the pattern-as-first-positional rule. The hand
  parser is shorter and behaves exactly like the spec.
- Text mode would raise `UnicodeDecodeError` on non-UTF-8 files and
  would make `\d` match Unicode digits; bytes mode matches GNU grep
  in the C locale and passes bytes through untouched.
