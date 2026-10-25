# TEST_PLAN — Spelling Correction Tool

Run from `spelling-correction/`:

```sh
python3 -m unittest discover -s tests -v
```

All tests use small synthetic dictionaries created in temp
directories (or in-memory dicts passed directly to the
library functions). No downloads, no network, no real
frequency dataset.

## Library tests (`tests/test_spell_correct.py`)

- Dictionary loading: bare words default to frequency 1;
  `word count` (space, tab, comma) parses the count;
  duplicates add; blank lines and `#` comments ignored;
  uppercase normalised to lowercase; missing file raises
  `FileNotFoundError`; a non-integer frequency raises
  `ValueError`.
- `is_correct`: known word true (case-insensitive),
  unknown word false.
- `edits1`: for a short word, each edit type is present in
  the generated set (a deletion, an insertion, a
  transposition, a replacement), and the count for a
  2-letter word matches the documented `54n + 25` bound
  after deduplication (at most that many distinct strings).
- Step 3 corrections, one test per edit type, e.g. a
  deletion typo corrected by insertion, an insertion typo
  by deletion, a transposed pair, a replaced letter.
- Ranking: when two distance-1 candidates exist, the more
  frequent wins; on a frequency tie, the alphabetically
  first wins.
- Distance preference: a distance-1 candidate beats a much
  more frequent distance-2 candidate.
- Distance 2: a word two edits away from the only dictionary
  word is corrected; a word with no candidate at distance
  1 or 2 echoes itself unchanged.
- `correct` echoes known words unchanged, including with
  different input capitalisation (lowercased result).
- `suggest` ordering: only the lowest available distance
  group is returned (distance 2 never mixed into a
  distance-1 result), frequency order inside the group,
  alphabetical ties, and `limit` truncation.
- Text correction: punctuation and spacing preserved,
  initial capital preserved, unknown words with no
  candidate left as typed.

## CLI tests (`tests/test_cli.py`, via subprocess)

- Word mode: `dict words...` prints `input correction`
  lines in order, including a correctly spelled word
  echoing itself (page's Step 5 shape).
- `--correct`: a sentence is printed corrected, with
  punctuation intact.
- `--file`: text read from a file is printed corrected.
- `--suggestions 2`: ranked suggestion list printed as
  `input: a, b`; a word with no suggestion prints `input:`.
- `--time`: output ends with a `Time : <num>ms <num> words
  per second` line matching the page's format.
- Errors: missing dictionary file exits non-zero with a
  stderr message; no words and no text option exits
  non-zero; `--suggestions` combined with `--correct`
  exits non-zero.

## Manual checks (done once, not in the suite)

- The page's Step 5 example shapes (`speiling` ->
  `spelling`, etc.) reproduce with a dictionary containing
  those words — the example words themselves are only
  meaningful against the author's Kaggle table, so the
  suite pins the shapes, not the author's exact table.
- `python3 spell_correct.py --help` reads sensibly.
