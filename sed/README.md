# sed — Build Your Own sed Tool

Coding Challenges entry 22, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A stream editor in Python 3 standard library only, single file
`ssed.py` (named `ssed` so it never shadows the system `sed`).
Implements the challenge page's Steps 1–6: substitution,
`-n` printing with line and regex addresses and address ranges,
`G` double-spacing, `d` deletion, and `-i` in-place editing,
plus the extras the parent task named (`s` flags, stdin/files).

## Usage

```sh
python3 ssed.py 's/this/that/g' file.txt
python3 ssed.py 's/"//g' test.txt
python3 ssed.py -n '2,4p' unquoted.txt
python3 ssed.py -n '/roads/p' unquoted.txt
python3 ssed.py G unquoted.txt
python3 ssed.py '/^$/d' unquoted.txt
python3 ssed.py -i 's/Life/Code/g' unquoted.txt
python3 ssed.py -i.bak 's/Life/Code/g' unquoted.txt   # keeps unquoted.txt.bak
cat unquoted.txt | python3 ssed.py -n '2,4p'
python3 ssed.py -e 's/a/b/g' -e '/^$/d' file.txt
python3 ssed.py -f script.sed file.txt
python3 ssed.py 's/a/b/g;p' file.txt                  # ; separates commands
```

- No file, or `-` as a file, reads standard input.
- `-n`: suppress automatic printing. `-i[SUFFIX]`: edit in place,
  optional backup suffix. `-e`/`-f`: repeatable scripts.
- Commands: `s`, `p`, `d`, `G`, `q`. Addresses: none, line number,
  `$`, `/regex/` (or `\cregexc`, optional `i` flag), and ranges
  `addr1,addr2`. `s` flags: `g`, `p`, a number, `i`, `w FILE`.
  See `docs/SPEC.md` for the full contract.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests run the real CLI as a subprocess and include a class that
compares output byte-for-byte against system `sed` on every
overlapping case.

## Deliberate divergences

- Regex dialect is Python `re` (the page's Easy difficulty), not
  GNU BRE/ERE. Concretely: `+`, `?`, `|`, `(...)` are metacharacters
  without backslashes (GNU BRE needs `\+`, `\?`, `\|`, `\(...\)`);
  `\<`/`\>` word boundaries, `\``/`\'` anchors, and interval
  `\ {m,n\ }` are not supported; `\w`, `\d`, `\s`, `\b` work in
  both. A pattern that is valid in one dialect may match
  differently in the other — the comparison tests only use
  patterns valid in both.
- Error text is prefixed `ssed:`, not GNU's `sed: -e expression #1,
  char N:` form (no character offsets are computed). Exit
  statuses match GNU sed 4.9: 1 for script errors, 2 for
  unreadable input files.
- Only the commands/options in `docs/SPEC.md` are implemented.
  This is not a full GNU sed clone: no hold-space commands
  beyond `G`, no `a`/`i`/`c`, no branching, no `y`, no `N`/`D`/`P`,
  no `-E`, no step addresses.
- With `-i` and stdin input, input passes through to stdout
  unchanged (GNU sed ignores `-i` on stdin the same way).
