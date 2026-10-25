# yq — a YAML query tool (like jq for YAML)

Build Your Own yq: https://codingchallenges.fyi/challenges/challenge-yq

`ccyq.py` is a small `yq` clone in a single Python 3 file, standard
library only. The YAML parser is hand-written — there is no YAML
parser in the stdlib, and PyYAML is neither imported nor vendored.

## Usage

```
python3 ccyq.py [FILTER] [FILE]
python3 ccyq.py tests/quotes.yaml            # Step 1: print the file
python3 ccyq.py '.quotes[0]' tests/quotes.yaml
python3 ccyq.py '.quotes[1] | .quote' tests/quotes.yaml
python3 ccyq.py '[.quotes[].quote]' tests/quotes.yaml
python3 ccyq.py '.quotes' < tests/quotes.yaml  # stdin also works
```

## Filters (challenge Steps 2–5)

- `.quotes`, `.[quotes]`, `.["quotes"]` — object identifier
- `.quotes?` — optional: wrong-type traversal yields `null`, not an error
- `.quotes[0]` — array index, zero-based; negative counts from the end;
  out-of-range yields `null`
- `.quotes[1] | .quote` — pipe
- `[.quotes[].quote]` — collect into an array (`[]` iterates)

Missing keys yield `null`. Errors (bad YAML, bad filter, wrong-type
traversal without `?`) exit 2 with a message on stderr.

## YAML subset supported

Block mappings and sequences (including indentless sequences and
sequence-of-mappings), plain / single- / double-quoted scalars, typed
scalars (int, float, bool, null, hex/octal), literal `|` and folded
`>` block scalars with chomping, comments, flow collections
(`[a, b]`, `{k: v}`), and `---` markers.

NOT supported: anchors/aliases, merge keys, tags, multi-document
streams, complex keys, tab indentation, multi-line quoted scalars,
and the "Going Further" yq operators (`select`, `map`, flags, `-i`, …).
Full detail, including every divergence from the challenge page, is in
`docs/SPEC.md`; design notes in `docs/DESIGN.md`.

## Tests

```
python3 -m unittest discover -s tests -v
```

38 tests, all passing: parser subset, all five challenge steps against
`tests/quotes.yaml` (fixture reconstructed from the page's printed
values — the author's Dropbox file was not downloaded; authors for
ids 2–4 are labelled filler in the fixture), emitter round-trips,
and CLI exit-code behaviour. No real `yq` binary is installed here,
so the oracle is the page's printed values plus hand-computed
expectations — not a comparison against real yq.
