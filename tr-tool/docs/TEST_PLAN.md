# tr Tool — TEST_PLAN

## How to run

```sh
cd ~/workspace/somecoolprojects/tr-tool
python3 -m unittest discover -s tests -v
```

No third-party packages. The suite is `tests/test_tr_tool.py`
(`unittest`, standard library only).

## Oracle

Where system `tr` is available (GNU coreutils 9.4 in this
environment), most CLI cases are byte-compared against it:
the test helper runs both `python3 tr_tool.py <args>` and
`tr <args>` on the same input bytes and asserts identical
stdout (and, for error cases, identical exit-status class:
non-zero) — except where this tool deliberately diverges
from GNU (see SPEC.md Divergences), in which case the test
asserts this tool's documented behaviour and says so in its
name/docstring. If `tr` is not on `PATH`, the oracle cases
skip cleanly (`shutil.which("tr")`) and the fixed-expectation
cases still run, so the suite stays green on a bare machine.

Note on oracle limits: GNU `tr` and the BSD man page quoted
by the challenge page are not identical (BSD-only classes,
`-u`, case-pairing of `[:lower:]`/`[:upper:]`). Oracle cases
are therefore chosen where GNU and the page agree, or where
the page example itself is the expectation. BSD-only behaviour
is never asserted via the GNU oracle.

## Coverage

### Page examples (Steps 1–5, fixed expectations)

- Step 1: `c C` on `coding challenges` → `Coding Challenges`.
- Step 2: `A-Z a-z` on the page's three Gutenberg lines →
  lowercase lines, exactly as printed on the page.
- Step 3: `[:upper:] [:lower:]` on the same lines.
- Step 4: `-d War` and `-d [:upper:]` on the same lines,
  matching the page's (slightly truncated) outputs — the
  `-d War` case is asserted on the page's first line only,
  where the page output is complete.
- Step 5: `-s AB` on `AAABBBCCC` → `ABCCC`; `-ds [:alnum:]
  [:space:]` behaviour on mixed input (delete alphanumerics,
  squeeze whitespace).

### Translation (oracle-compared unless noted)

- Single characters, multiple characters, ranges, mixed
  literal+range sets (`a-cx-z` style).
- Shorter string2 pads with its last byte; longer string2
  ignores the excess; `-t` truncates string1 instead.
- Upper/lower via ranges and via classes, both directions.
- Escapes: `\n \t \r \\ \a \b \f \v`, octal `\040 \101`,
  `\n` as a set member translating newline itself.
- Literal hyphen: leading, trailing, escaped (`\-`), and a
  hyphen between classes (not a range).
- Classes: every supported class as string1 and as string2,
  including `[:lower:]` → `[:upper:]` pairing.
- Complement `-c` and `-C` (synonyms): translate, including
  complement with a range set.
- Duplicate byte in string1: last pairing wins (oracle case:
  `tr 'aab' 'XYZ'` maps `a` to `Y`).
- Empty string1 → no-op, exit 0 (oracle case). Empty string2
  when translating a non-empty string1 → error, exit 1.
  Reversed range → error, exit 1. Unknown class → error,
  exit 1. Fill repeat `[c*]` in string1 → error, exit 1;
  explicit repeat `[c*n]` in string1 → expands (oracle case).
  Trailing backslash → literal backslash (oracle case;
  system `tr` additionally warns).
- Repeat in string2: `[x*3]`, `[x*]` (fill), `[x*0]`
  (fill), octal count `[x*010]`.
- Equivalence `[=a=]` in both sets.
- `--` handling: a set starting with `-` via `--`.
- No operands, one operand for plain translate, three
  operands, `-d` with two operands and no `-s`, `-ds`
  with one operand → all errors, exit 1.

### Delete (oracle-compared unless noted)

- `-d` literal, range, class, escapes; `-d` with `-c`
  (delete everything except the set); `-d` of a class that
  leaves only punctuation/whitespace.
- `-d` alone leaves all other bytes, including newlines
  and NUL, untouched.

### Squeeze (oracle-compared unless noted)

- `-s` alone: runs collapse, non-listed runs untouched,
  single instances untouched.
- Translate + `-s`: squeeze set is string2 as written, not
  the padded mapping (the `tr -s 'ab' 'A'` → `ABBB` case
  that pins this down).
- `-ds`: delete then squeeze, including the page's
  `-ds [:alnum:] [:space:]` shape.
- `-cs` (complement squeeze) and `-cds`.
- Squeeze across chunk boundaries: a run longer than the
  64 KiB chunk size is squeezed to one byte (regression
  test for the carried `prev` state; uses a run of
  200,000 bytes).

### Bytes and scale (Step 6)

- Binary input: all 256 byte values through translate,
  delete, and squeeze, byte-compared against system `tr`.
- NUL bytes pass through unchanged unless deleted or
  translated.
- Large input (several megabytes, mixed content) through
  translate and through delete+squeeze, byte-compared
  against system `tr` — the Step 6 scale property.
- Empty input → empty output, exit 0, in every mode.

### Unit tests (no subprocess)

- `parse_set` directly: literals, ranges, classes, escapes,
  octal, repeat sentinels, equivalence, literal hyphen
  positions, and each error case raising `TrError`.
- `build_translation` directly: padding, truncation,
  complement, first-pairing-wins.
- `squeeze_bytes` helper behaviour across a chunk boundary
  (prev byte carried in).

## What is NOT tested

- BSD-only classes (`rune`, `special`, `ideogram`,
  `phonogram`): only that they are rejected with exit 1 —
  there is no correct byte-level expectation to test against.
- Locale-dependent behaviour: tests run in the C locale;
  class definitions are fixed ASCII.
- Interactive terminal behaviour (Ctrl-D/EOF): EOF on a
  pipe is the same code path and is what the tests use.
- The Gutenberg download from Step 0 (no network in tests);
  the page's Gutenberg lines are embedded as literals.
