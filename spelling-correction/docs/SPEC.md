# SPEC — Spelling Correction Tool

Source: https://codingchallenges.fyi/challenges/challenge-spelling-correction/
Page slug used: `challenge-spelling-correction` — first guess, no
404, no correction needed. (This is Coding Challenge #98 on the
challenge's Substack mirror; the fyi page itself carries no number.)

Challenge summary, mapped to this build:

- Step Zero: get training data — a set of words and the
  frequency they occur in a large body of text. The page's
  author used the English Word Frequency dataset from Kaggle.
- Step 1: parse the training data into a word-frequency table.
- Step 2: a word in the table is correctly spelled.
- Step 3: for a misspelt word, generate all words one edit away
  (deletion, insertion, transposition, replacement), keep only
  those in the table, and suggest the most frequent one.
- Step 4: extend to Levenshtein distance two, still preferring
  the lowest distance first, then the highest frequency within
  that distance.
- Step 5 (optional): time a list of corrections and print
  `Time : <ms>ms <words-per-second> words per second`.
- Going Further: Bloom-filter speed-up, distance > 2, trigram /
  phonetic / context approaches — all out of scope (see
  DESIGN.md divergences).

## Dictionary file format (this build's choice)

The page does not fix a file format, so this build defines one
and documents it:

- One word per line, lower- or mixed-case (normalised to
  lowercase on load).
- Optionally followed by a frequency: `word 123`, `word\t123`,
  or `word,123`. A bare word means frequency 1.
- Blank lines and lines starting with `#` are ignored.
- Duplicate words add their frequencies together.

This keeps Step Zero/1 testable without a Kaggle download:
tests use small synthetic dictionaries in this format, and a
user can supply any real frequency list in the same shape.

## CLI contract

```
python3 spell_correct.py DICT word [word ...]
python3 spell_correct.py DICT --correct "some text"
python3 spell_correct.py DICT --file input.txt
python3 spell_correct.py DICT --suggestions 3 word
python3 spell_correct.py DICT --time word [word ...]
```

- Word mode (default): one `input correction` line per word,
  in input order — the page's Step 5 example shape, where a
  correctly spelled word echoes itself (`coding coding`).
- `--correct TEXT`: print the text with each word replaced by
  its correction (capitalisation of the first letter is
  preserved; see DESIGN.md).
- `--file PATH`: same as `--correct`, but the text is read
  from the file.
- `--suggestions N`: in word mode, print up to N ranked
  suggestions per word instead of the single best correction,
  as `input: suggestion1, suggestion2, ...`; a word with no
  suggestion prints `input:` (empty list).
- `--time`: append the page's Step 5 timing line after the
  word-mode output: `Time : <ms>ms <wps> words per second`.
- Errors: missing dictionary file, unreadable dictionary, or
  no words/text to correct exit non-zero with a message on
  stderr. No words and no `--correct`/`--file` is a usage
  error (reading stdin was not added — see DESIGN.md).

## Library contract (single file, stdlib only)

- `load_dictionary(path) -> dict[str, int]`
- `is_correct(word, freq) -> bool`
- `edits1(word) -> set[str]` (deletion, insertion,
  transposition, replacement over `a-z`)
- `known(words, freq) -> set[str]`
- `candidates(word, freq) -> set[str]` (known words at
  distance 1, else distance 2, else empty)
- `rank(words, freq) -> list[str]` (highest frequency first,
  alphabetical tie-break)
- `suggest(word, freq, limit=None) -> list[str]`
- `correct(word, freq) -> str` (the word itself if correct
  or if no candidate exists)
- `correct_text(text, freq) -> str`

## Success criteria (verifiable, see TEST_PLAN.md)

- Known words echo unchanged; unknown words with a
  distance-1 neighbour get the most frequent neighbour.
- Distance-2 corrections work, and distance-1 always beats
  distance-2 even when the distance-2 word is more frequent.
- Rank order is frequency-descending with a deterministic
  alphabetical tie-break.
- CLI word mode, `--correct`, `--file`, `--suggestions`,
  and `--time` all behave as above, including the page's
  example word shapes.
