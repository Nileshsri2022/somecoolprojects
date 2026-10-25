# spelling-correction — Build Your Own Spelling Correction Tool

Coding Challenge #98 (Substack numbering), worked in
`somecoolprojects/` (entry 68). Docs first, then code —
see `docs/`.

Unlike the Bloom-filter spell checker (entry 41), which
stores no words and can only say "probably correct", this
tool stores a word-frequency table and *suggests*
corrections: it generates every word one edit away
(deletion, insertion, transposition, replacement), keeps
the ones in the table, and picks the most frequent —
falling back to distance two when distance one yields
nothing, always preferring the lowest distance first.

## Usage

Dictionary format: one word per line, optionally followed
by a frequency (`word 123`, `word<TAB>123`, or
`word,123`); a bare word means frequency 1.

```sh
# Word mode: one "input correction" line per word, in order
# (a correctly spelled word echoes itself, per the page's
# Step 5 example shape)
python3 spell_correct.py dict.txt speiling misteke executionw mekanism coding chalenges
speiling spelling
misteke mistake
executionw execution
mekanism mechanism
coding coding
chalenges challenges

# Correct a whole sentence, preserving punctuation/capitalisation
python3 spell_correct.py dict.txt --correct "Speiling is a misteke."
Spelling is a mistake.

# Correct a file
python3 spell_correct.py dict.txt --file input.txt

# Ranked suggestions instead of a single correction
python3 spell_correct.py dict.txt --suggestions 3 speiling
speiling: spelling

# Step 5 timing (opt-in)
python3 spell_correct.py dict.txt --time speiling misteke
speiling spelling
misteke mistake
Time : 20.026833ms 299.6 words per second
```

(The last timing line shows the page's example values, not
a measured run — actual output varies with the dictionary
and machine.)

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use small synthetic dictionaries only (no downloads)
and cover dictionary parsing, each Step 3 edit type,
frequency ranking, the alphabetical tie-break, distance-1
beating a more frequent distance-2 word, distance-2
correction, text correction, and CLI word / `--correct` /
`--file` / `--suggestions` / `--time` modes end-to-end.

## Page slug

`challenge-spelling-correction` — first guess, no 404, no
correction needed:
https://codingchallenges.fyi/challenges/challenge-spelling-correction/

## Divergences (documented in `docs/DESIGN.md`)

- Dictionary file format is defined by this build (the page
  fixes none): `word [frequency]` per line.
- The Kaggle English Word Frequency dataset is not
  downloaded or bundled; the loader accepts any real
  frequency list in the documented format.
- Timing is opt-in via `--time` (Step 5 is optional on
  the page).
- Alphabetical tie-break added to the page's ranking rule
  (distance, then frequency) for determinism.
- No Bloom filter, trigram, phonetic, or context support
  (page's Going Further, out of scope).
