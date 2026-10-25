# sed — SPEC

Source: https://codingchallenges.fyi/challenges/challenge-sed/
(slug `challenge-sed`; guessed slug worked first try, no 404 correction needed.)

The page defers to `man sed` and defines the work in Steps 0–6:

- Step 0: test data — quotes file (the page fetches quotes via
  dummyjson; we use a small local fixture instead, same shape).
- Step 1: substitution — `ccsed s/this/that/g filename` writes the
  result to stdout, e.g. `s/\"//g` strips quotes.
- Step 2: `-n` + line range — `ccsed -n '2,4p' filename` prints only
  lines 2–4.
- Step 3: `-n` + regex address — `ccsed -n /roads/p filename` prints
  only lines containing the pattern.
- Step 4: `G` — `ccsed G filename` double-spaces the file (appends a
  blank line after each line).
- Step 5: delete — `ccsed /^$/d filename` strips blank lines.
- Step 6: `-i` — `ccsed -i 's/Life/Code/g' filename` edits in place.

## Implemented behaviour (Easy difficulty: Python `re`)

Usage:

```
python3 ssed.py [-n] [-i[SUFFIX]] [-e SCRIPT]... [SCRIPT] [FILE]...
python3 ssed.py -f SCRIPTFILE [FILE]...
```

- No FILE, or `-` as a FILE, reads standard input. Multiple files are
  processed in order; line numbers and `$` are per file (as in GNU sed
  without `-s`... see Divergences: `$` is per file, line numbers reset
  per file — matching GNU sed's default for line addresses).
- Options: `-n` (suppress automatic printing), `-i` (edit in place;
  `-iSUFFIX` writes a backup copy to `FILE+SUFFIX`, `-i` alone writes
  no backup), `-e SCRIPT` (repeatable; scripts run in order),
  `-f FILE` (read script from file, repeatable), `--` (end of options).
  Combined short options are accepted (`-ne '...'`, `-ni`).
- Commands (one per line in a script; `;` also separates commands
  except inside an `s` command's delimiters — see DESIGN.md):
  `s`, `p`, `d`, `G`, `q`, `y` is NOT implemented.
  - `s/pattern/replacement/flags`: any delimiter character may be used
    (`s|a|b|`, `s#a#b#`); a delimiter escaped with `\` inside the
    pattern/replacement does not end the field. Flags: `g` (all
    occurrences), `p` (print the pattern space if a substitution was
    made), a decimal number (substitute only that occurrence),
    `i` (case-insensitive match), `w FILE` (append lines on which a
    substitution was made to FILE; the file is truncated when the
    script is parsed). `g` and a number may not be combined.
    An empty pattern reuses the last regex used (as in GNU sed).
    Replacement: `&` = whole match, `\1`–`\9` = capture groups,
    `\&` / `\\` are literal; an unmatched group expands to empty.
  - `p`: print the pattern space (in addition to the automatic print,
    unless `-n`).
  - `d`: delete the pattern space and start the next cycle
    (skips the automatic print and any later commands for this line).
  - `G`: append a newline plus the (empty) hold space to the pattern
    space, i.e. a blank line after the line.
  - `q`: print the pattern space (unless `-n`) and quit — no further
    lines or files are processed.
- Addresses: none (every line), a line number (1-based), `$` (last
  line of the file), `/regex/` (optionally `/regex/I` for
  case-insensitive — capital `I` only, as in GNU sed; a lowercase
  `i` after an address would be the insert command in GNU, so it
  is not accepted as a flag here), and ranges `addr1,addr2` where
  each side is a line number, `$`, or `/regex/`. Address `0` is an
  error. A range
  whose end is a line number less than or equal to its start line
  matches only the start line. A range ending on a regex is not
  tested on the line that started the range. An address regex may use
  any delimiter (`\cregexc`, e.g. `\|foo|p`); `\/` inside does not
  end it. `%` and `~` (step) addresses are NOT implemented.
- Regex dialect: Python `re` (Easy difficulty on the page).
  Differences from GNU BRE/ERE are documented in README.md.
- Output terminators (verified against GNU sed 4.9, including
  multi-file runs): every output chunk ends with `\n`, except
  possibly the very last chunk of a destination stream, which
  has no terminator when its source line had none and its
  pattern space does not end with `\n`. Consequences: a plain
  unterminated last line stays unterminated; a `G`-doubled
  unterminated line ends with `\n\n` (its pattern ends with
  `\n`, so the final chunk still gains one); an unterminated
  last line of a non-final input file gains `\n` because more
  output follows. `w`-file chunks follow the same rule within
  their own stream. With `-i`, output replaces the file;
  without `-i`, output goes to stdout. With `-i` and stdin
  input there is no file to edit, so input is copied through
  unchanged to stdout (GNU sed ignores `-i` on stdin; we do the same
  rather than erroring).
- Errors: script errors (unterminated `s`, unknown command, bad
  address, bad flag) print `ssed: ...` to stderr and exit 1.
  Unreadable/missing input files print `ssed: can't read ...` to
  stderr, processing continues with the next file, and the exit
  status is 2 (matching GNU sed 4.9). A missing script argument
  (`-e` with nothing after it, or no script at all) is a usage
  error, exit 1.

## Deliberate non-goals

- No hold-space commands beyond `G` (`h`, `H`, `x`, `g`), no `a`/`i`/`c`
  text commands, no branching (`:`, `b`, `t`), no `y`, no `r`/`R`/`w`
  command (only the `w` flag of `s`), no multi-line commands
  (`N`, `D`, `P`), no extended-regex flag (`-E`/`-r`), no
  `--sandbox`, no line-length tricks. The page asks for none of these;
  adding them would violate "minimum code, nothing speculative".
