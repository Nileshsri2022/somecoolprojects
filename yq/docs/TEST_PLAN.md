# yq — TEST PLAN

Suite: `tests/test_ccyq.py`, run with
`python3 -m unittest discover -s tests -v` from the `yq/` directory
(or `python3 tests/test_ccyq.py`). All tests use only the standard
library. Exit code 0 = all green.

## Coverage map (challenge step → tests)

- Step 1 (print whole file): identity filter, no-filter CLI form,
  stdin form, whole-document parse of `quotes.yaml` (5 quotes, ids
  1–5, folded scalars for 3–5), exact stdout for a small document.
- Step 2 (object identifier): `.quotes`, `.[quotes]`, `.["quotes"]`,
  `.['quotes']`, `.quotes?` on present and missing keys,
  `.["quotes"]?`, optional suppressing a wrong-type traversal
  (`.quote?` on a string input → null, no error), missing key →
  null without `?`, nested `.a.b` chaining.
- Step 3 (array index): `.quotes[0]` exact mapping, `[1]`, `[4]`
  (last), `[-1]`, out-of-range `[5]` and `[99]` → null, exit 0,
  negative out-of-range `[-99]` → null, index into a non-sequence →
  error exit 2 (and `?` variant → null), `.[0]` bracket form.
- Step 4 (pipe): `.quotes[1] | .quote` exact page value,
  multi-stage pipes, pipe after iteration (`.quotes[] | .author`
  collected via constructor), pipe into a missing key → null.
- Step 5 (array collect): `[.quotes[].quote]` exact 5-element list
  matching the page (folded scalars joined to single lines),
  `[.quotes[].author]`, `[.quotes[].id]`, bare `.quotes[]`
  multi-output with `---` separators, empty input sequence → `[]`.
- Parser subset: block mappings/sequences, nesting, indentless
  sequences, sequence-of-mappings, plain/single/double-quoted
  scalars, ints/floats/bools/null/`~`/empty, hex/octal, folded `>-`
  and literal `|-`/`|`/`>` block scalars, comments (full-line and
  trailing, `#` inside quotes and apostrophes preserved), flow
  `[a, b]` / `{k: v}`, `---` skip, tab indentation rejected,
  anchors rejected, second document rejected, malformed mapping
  (missing colon value handling) rejected where ambiguous.
- Emitter: round-trip parse → emit → parse equality for mappings,
  sequences, nested values, typed scalars, strings needing quotes
  (`"true"`, `"a: b"`, `""`, leading `- `), multi-line strings.
- CLI: unknown file → exit 2; malformed YAML → exit 2 with empty
  stdout; malformed filter → exit 2; missing-key query → exit 0
  with `null`.

## What is NOT tested (and why)

- Comparison against a real `yq` binary: none is installed here.
  Oracle is the page's printed values + hand-computed expectations.
- The author's Dropbox file: not downloaded; fixture reconstructed
  from page text (see SPEC divergence 2).
- "Going Further" yq operators: out of scope, untested by design.
