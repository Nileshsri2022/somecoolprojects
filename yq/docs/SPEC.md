# yq — SPEC

Challenge: Build Your Own yq (Coding Challenges)
Page: https://codingchallenges.fyi/challenges/challenge-yq
Tool name (per page): `ccyq`. This project implements it as `ccyq.py`
(plus a thin `ccyq` launcher is NOT provided — run `python3 ccyq.py ...`).

## Challenge steps (as written on the page)

- **Step Zero** — Set up the environment. The page links test YAML from
  the author's Dropbox. That download was NOT fetched (third-party file
  host, not needed): the test fixture `tests/quotes.yaml` below was
  written from the values the page itself prints (all five quote
  texts; authors for ids 1 and 5 only — authors for ids 2–4 are
  invented filler, labelled as such in the fixture), so the suite is
  self-contained.
- **Step 1** — Open a YAML file, read it and print it.
  `ccyq quotes.yaml` prints the whole document.
- **Step 2** — Object identifier: `.quotes`, `.[quotes]`, `.["quotes"]`,
  and the optional (`?`) extension: `.quotes?`, `.["quotes"]?`.
  Only the selected value is printed.
- **Step 3** — Array index: `.[<number>]`, zero-indexed, e.g.
  `.quotes[0]`. Out-of-range indices must be tested.
- **Step 4** — Pipe operator `|`: feed the left filter's output into
  the right filter, e.g. `.quotes[1] | .quote`.
- **Step 5** — Collect output as an array by wrapping a filter in
  square brackets, e.g. `[.quotes[].quote]`. This step implicitly
  requires the iterate operator `[]` (used in the page's own example
  but never given its own step); `[]` is implemented and documented
  here as part of Step 5.
- **Going Further** — "read yq's documentation and implement as many
  options as possible." NOT pursued beyond the steps above, except
  for the small extras listed under "Deliberate extras" — the core
  steps are the contract.

## CLI contract

```
python3 ccyq.py [FILTER] [FILE]
python3 ccyq.py FILE            # Step 1: no filter, print whole document
python3 ccyq.py FILTER FILE
python3 ccyq.py FILTER          # reads YAML from stdin
python3 ccyq.py                 # reads YAML from stdin, identity filter
```

- One-argument disambiguation: if the single argument names an existing
  file (or ends in `.yaml`/`.yml`), it is the file; otherwise it is a
  filter read from stdin.
- Output is YAML (re-emitted from the parsed value, not the raw input
  text), so Step 1 output is semantically identical but whitespace /
  quoting may differ from the input file.
- Exit 0 on success; exit 2 with a message on stderr (and no stdout)
  on a YAML parse error or a query error (see "Error semantics").
- A document that parses to nothing (empty file / only comments)
  prints `null` followed by a newline.

## Filter language (implemented)

| Syntax | Meaning |
|---|---|
| `.` (or empty filter) | Identity: the whole input value. |
| `.field` | Mapping key `field`. |
| `.[field]` | Same, unquoted bracket key (page Step 2). |
| `.["field"]` / `.['field']` | Same, quoted bracket key (page Step 2). |
| `.field?`, `.["field"]?`, `.[0]?` | Optional: any error from that step yields `null` instead of failing (see below). |
| `.[<number>]` | Sequence index, zero-based; negative counts from the end (`-1` = last). |
| `[]` | Iterate: one output per sequence element. Only meaningful inside a pipe or an array constructor; as the final step of a bare filter it prints each element as its own YAML document-ish block separated by `---`? No — see "Iteration output" below. |
| `filter \| filter` | Pipe: left output(s) feed the right filter. |
| `[filter]` | Array constructor: collect all outputs of `filter` into one sequence. |

Chaining is free: `.quotes[0].quote`, `.a.b[2].c`, `.quotes[] | .author`,
`.quotes[1] | .quote` all work. A filter may start with `.` or with a
bracket step (`.quotes`, `.[0]` after a pipe stage).

### Iteration output

A bare filter ending in `[]` (e.g. `.quotes[]`) prints each element
in turn, each as its own YAML value, separated by a line `---` between
consecutive outputs (jq-style multi-output, YAML-document style).
Inside `[ ... ]` the elements are collected into a single sequence
instead — that is the Step 5 form and the normal way to use `[]`.

### Error semantics (documented, tested)

- Missing mapping key (no `?`): yields `null` — this matches real
  `yq`/`jq` behaviour (a missing key is `null`, not an error).
- Indexing a non-sequence, keying a non-mapping, or applying `[]` to
  a non-sequence: an error, EXCEPT when the step carries `?`, in
  which case that stage yields `null`.
- Out-of-range index (no `?`): yields `null` (same as real `yq`/`jq`),
  NOT an error. Negative index beyond the start likewise yields `null`.
  Step 3 explicitly asks that out-of-range indices be tested; they are
  (null, exit 0).
- Malformed filter (unbalanced brackets/quotes, empty pipe stage,
  trailing garbage): error, exit 2.
- Malformed YAML: error, exit 2.

## YAML subset supported (hand-written parser, stdlib only)

The parser is written from scratch in `ccyq.py`; PyYAML is NOT vendored
and NOT imported (there is no YAML parser in the Python standard
library). Supported:

- Block mappings, nested by indentation (spaces only; a tab in
  indentation is an error).
- Block sequences (`- item`), including sequences nested under a
  mapping key at the same indentation as the key (indentless sequences)
  and mapping values that are the first item of a sequence
  (`- id: 1` followed by more-indented keys of the same mapping).
- Scalars: plain, single-quoted, double-quoted (with `\"`, `\\`, `\n`,
  `\t` escapes; other `\x` escapes are left literal after the backslash
  except the four above).
- Typed scalars: `true`/`false` (also `True`/`False`/`TRUE`/`FALSE`),
  `null`/`Null`/`NULL`/`~`/empty value, integers (decimal, `0x` hex,
  `0o` octal, sign, underscores), floats (decimal, exponent,
  `.inf`/`-.inf`/`.nan` case-insensitive). Anything else plain is a
  string. Quoted scalars are always strings, even `"123"`.
- Block scalars: literal `|` and folded `>` with chomping indicators
  `-` (strip), `+` (keep), default clip, and an explicit indentation
  indicator digit is accepted and honoured when present
  (e.g. `|-2`); the folded style joins single newlines to spaces and
  keeps blank-line paragraph breaks, per YAML.
- Comments: `#` starts a comment when preceded by whitespace (or at
  line start) outside quotes; full-line comments and blank lines are
  skipped except inside block scalars.
- Flow collections: `[a, b, c]` and `{k: v, k2: v2}`, nestable, with
  quoted/plain scalars inside.
- `---` document-start and `...` document-end lines are skipped.
- Multi-line plain scalars (continuation lines more-indented than the
  key) are folded with spaces — YAML-legal, but rare; supported for
  simple cases (one continuation style, no flow interplay).
- Top level may be a mapping, a sequence, or a bare scalar.

## NOT supported (honest scope limits)

- Anchors (`&a`), aliases (`*a`), merge keys (`<<`), tags (`!!str`),
  directives (`%YAML`, `%TAG`): a line introducing any of these in a
  key/value position is rejected or, for a plain scalar value starting
  with `&`/`*`/`!`, treated as a parse error rather than silently
  mis-parsed. (A `*` inside a longer plain scalar, e.g. `2 * 3`, is
  still an ordinary string.)
- Multi-document streams: only the first document is read; a second
  `---` after content is an error, not a second document.
- Complex keys (`? key` explicit-key syntax), sets, binary scalars.
- Tab indentation; mixed tabs/spaces.
- Multi-line quoted scalars (a quoted scalar must close on its line).
- Flow scalars spanning lines, block-scalar header comments.
- Duplicate keys: last value wins (documented; not an error).
- Unicode is passed through as-is (Python `str`); no special handling.
- No output flags (`-r`, `-o=json`, `--arg`, …), no in-place editing
  (`-i`), no colour, no `eval`/`env` operators, no `select`/`map`/
  `sort`/`keys` functions, no comma operator, no string interpolation.
  None of these appear in Steps 0–5; "Going Further" is out of scope
  except as noted above.

## Deliberate extras (beyond the page, small and documented)

- Stdin input when no file is given; identity filter when no filter
  is given.
- Negative array indices (`[-1]`).
- Flow collections (`[a, b]`, `{k: v}`) — cheap to support in the same
  parser and useful in fixtures.
- `.[0]` bracket-index form and chaining after pipes (implied by the
  page's own examples, e.g. `.quotes[1] | .quote`).
- Output emitter quotes strings that would otherwise re-parse as a
  different type or break structure (e.g. `true` as a string, `a: b`,
  leading `- `, empty string as `""`, `#` comments).

## Deliberate divergences from the page

1. Step 1 output is re-emitted YAML, not a byte copy of the input.
   Values are identical; formatting (quote style, folded vs plain
   wrapping) may differ. Tests assert on parsed values, plus exact
   output for simple documents.
2. The Dropbox test file was not downloaded; `tests/quotes.yaml` was
   reconstructed from the page's own printed values (all five quote
   texts and the authors shown for ids 1 and 5, including the `>-`
   folded scalars for ids 3–5; authors for ids 2–4 are invented
   filler, labelled as such in the fixture). It is a fixture, not a
   claim to be the author's file.
3. Optional `?` semantics: in real `yq`, `.foo?` on a missing key and
   on a wrong-typed input both give `null`; here missing keys give
   `null` with or without `?`, and `?` additionally suppresses
   wrong-type errors. This matches observable real-yq output for all
   tested cases; only the error-vs-null boundary for missing keys is
   collapsed, deliberately, because the page never defines it.
4. No `ccyq` executable install step: the deliverable is `ccyq.py`
   run under Python 3. A shell alias/wrapper is a one-liner for the
   user and is not faked here.

## Oracle

No real `yq` binary is installed in this environment (`which yq`
returned nothing), so outputs were NOT compared against real yq.
The oracle is: (a) the expected values printed on the challenge page
itself (Step 1/3/4/5 examples), and (b) hand-computed expected values
in the unit tests. This is stated here rather than claiming a yq
comparison that did not happen. `jq` is installed but is a JSON tool,
not a YAML oracle, and was not used as one.
