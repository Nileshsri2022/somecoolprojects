# TEST_PLAN — yaml-parser

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

Every test is in `tests/test_yaml_parser.py` and uses only the
standard library (`unittest`, `subprocess`, `tempfile`, `math`).

## Step 1 — Simple nested mapping (page example, verbatim)

- `name: Coding Challenges` + nested `challenge: name: YAML Parser`
  parses to exactly `{"name": "Coding Challenges", "challenge":
  {"name": "YAML Parser"}}`.

## Step 2 — Scalar typing (page example, verbatim)

- All ten page keys: `true` -> True, `off` -> False, `null` ->
  None, `value` -> `"value"`, `101` -> 101, `~` -> None,
  `0x12d4` -> 4820, `023332` -> 9946, `.inf` -> Infinity,
  `.NAN` -> NaN (checked with `math.isinf` / `math.isnan`).
- Boolean variants: `yes/no/on/off/True/FALSE/Y/N` and case
  variants; `null/Null/NULL`, empty value -> None.
- Numbers: negative int, `+42`, `0o17`, `0xFF`, `3.14`,
  `-0.5`, `1e3`, `-.inf`, `.nan`; `08` falls back to decimal 8;
  `1:30` stays a string; `2026-10-25` stays a string.
- Plain strings keep internal spaces; surrounding spaces are
  stripped; `a#b` keeps the `#`.

## Step 3 — Quoted, folded, literal strings (page examples)

- `quoted: "Coding Challenges\n"` ends with a real newline;
  `non: Coding Challenges\n` ends with backslash + `n`.
- Double-quote escapes: `\t`, `\"`, `\\`, `\x41` -> `A`.
- Single-quoted: `'it''s'` -> `it's`; backslash stays literal.
- Folded `>`: page example joins to one line plus clip's
  trailing newline; `>-` strips it; `>+` keeps blank lines.
- Literal `|`: page example keeps newlines plus clip's trailing
  newline; `|-` strips it.
- Quoted keys: `"my key": 1` and `'k': 2` work.

## Step 4 — Objects and arrays (page examples)

- Block sequence under a key, including the page's 1-space
  indent and the flush-with-key form.
- Flow sequence `[1, 2]`, flow mapping
  `{ writes: Coding Challenges, loves: dogs, hates: meetings }`,
  nested flow (`{a: [1, {b: 2}]}`), flow in a sequence item.
- Sequence of mappings (`- name: a` + continuation keys),
  nested sequences, nested mapping in a sequence item,
  top-level sequence, top-level scalar, empty document -> None.
- Comments: full-line and trailing, not applied inside quoted
  strings or block scalars.
- `---` leading marker and `...` trailing marker accepted.

## Step 5 — Errors (must name a line number)

- Tab indentation; unexpected (over-)indentation in a mapping;
  a mapping line with no colon; duplicate key in one mapping;
  unclosed double quote, unclosed single quote, unclosed flow
  `[` and `{`; trailing junk after a quoted scalar; unknown
  double-quote escape; anchor (`&a`), alias (`*a`), tag
  (`!!str`), and directive (`%YAML`) rejected; second `---`
  rejected; explicit-indentation block indicator (`|2`)
  rejected; a block scalar whose content is not indented
  yields `""` (clip of empty content), not an error.

## CLI level (subprocess)

- File argument prints the JSON equivalent of the page's
  Step 1 example.
- No argument reads stdin.
- A parse error exits non-zero with the message on stderr and
  nothing on stdout.
- A missing file exits non-zero with an error on stderr.
