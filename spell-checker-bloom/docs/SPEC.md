# SPEC — Spell Checker Using A Bloom Filter (somecoolprojects entry 41)

Source challenge: "Build Your Own Spell Checker Using A Bloom Filter",
Coding Challenge #53.

## Page slug / 404 caveat

The codingchallenges.fyi page for this challenge could NOT be
reached under either slug tried:

- `https://codingchallenges.fyi/challenges/challenge-spell-checker/`
  -> HTTP 404
- `https://codingchallenges.fyi/challenges/challenge-bloom-filter/`
  -> HTTP 404

No further fyi slugs were guessed. The build below is taken from
the challenge's canonical full text, Coding Challenge #53 on
Substack (`https://codingchallenges.substack.com/p/coding-challenge-53-bloom-filter`,
published 2024-03-16), which is the same challenge (same title,
same steps, same `CCBF` file format and same `ccspellcheck`
examples) and is linked from the codingchallenges.fyi tag pages.
If the fyi slug is later found, re-check the steps against it;
nothing here depends on a detail that exists only in the
Substack rendering. Reconciliation 2026-10-25: the Substack
source was read directly and its steps match this build
(dictionary build, Bloom sizing formulas, FNV suggestion,
`CCBF` header layout, load/validate, word testing CLI).
Hash count follows the sizing formula (7 for the documented
defaults), not the page example's 4 — a formula outcome,
not a mismatch.

## Page steps (verbatim intent)

- Step 0 — Set up the environment. Get a dictionary file for
  testing (on Unix: `/usr/share/dict/words`, copied to
  `dict.txt`).
- Step 1 — Implement the Bloom filter (TDD suggested):
  1. From the expected item count `n` and the tolerable
     false-positive probability `p`, derive the bit-array size
     and the number of hash functions (standard formulas,
     per the Bloom filter Wikipedia page).
  2. Create a bit array, all bits zero.
  3. Insert an item by applying the hash functions and setting
     the corresponding bits to one.
  4. Query an item by applying the hash functions: if any
     corresponding bit is zero, the item is definitely NOT in
     the set; if all are one, it is probably in the set.
  - Hash functions may come from the standard library, be
    home-grown, or be an existing one implemented by hand;
    the page suggests Fowler-Noll-Vo (FNV).
- Step 2 — Read a dictionary file and insert its words into
  the filter, e.g. `ccspellcheck -build dict.txt`, saving the
  result (the author's file is called `words.bf`).
- Step 3 — Save the Bloom filter to disk with a header, all
  big-endian:
  - first 4 bytes: identifier `CCBF`
  - next 2 bytes: version number
  - next 2 bytes: number of hash functions used
  - next 4 bytes: number of bits used for the filter
  - then the bit array itself
  - Example header (from the page): identifier `CCBF`,
    version 1, 4 hash functions, `0x003d0900` bits.
  - The saved filter is much smaller than the dictionary
    (page example: 2.4M dictionary -> 492K filter).
- Step 4 — Load the Bloom filter from disk, validating the
  header (type and version as expected).
- Step 5 — Test words given on the command line, e.g.
  `ccspellcheck hi hello word concurrency coding challenges
  imadethis up`, printing:
  ```
  These words are spelt wrong:
   coding
   challenges
   imadethis
  ```
  (Those three are wrong only because they are absent from
  the author's chosen dictionary, not because the filter
  rejected them for another reason.)
- Going further (NOT built, see DESIGN.md): a filter to stop
  users picking common passwords at sign-up.

## Implemented surface (this CLI)

Single file `spell_checker.py`, Python 3 standard library only.

Build a filter from a dictionary file:

```sh
python3 spell_checker.py -build dict.txt [words.bf]
python3 spell_checker.py -build dict.txt -o words.bf --fp-rate 0.01
```

- Default output is `words.bf` in the current directory.
- Default target false-positive rate is `0.01` (1%).
- Words are lowercased; blank lines are skipped; duplicate
  dictionary lines count once (see DESIGN.md).
- The filter size / hash count are derived from the number of
  distinct words actually loaded, not from the raw line count.

Check words against a saved filter:

```sh
python3 spell_checker.py words.bf hi hello word concurrency coding challenges imadethis up
```

- Prints nothing (exit 0) when every word is probably spelt
  correctly.
- Otherwise prints exactly the page's format:
  ```
  These words are spelt wrong:
   coding
   challenges
   imadethis
  ```
  (one leading space before each wrong word, as on the page),
  and exits 0. The exit code is deliberately 0: the page
  shows no exit-code contract, and a listing is the output.
- Words are checked case-insensitively (lowercased), matching
  the lowercasing applied at build time.

Library surface (importable from `spell_checker.py`):

- `BloomFilter(num_bits, num_hashes)` — bit array, `add`,
  `__contains__` (`in`), `bits_set`, `estimated_false_positive_rate(n)`.
- `optimal_parameters(n, fp_rate)` -> `(num_bits, num_hashes)`.
- `build_filter(words, fp_rate)` — sizing + insertion.
- `load_dictionary(path)` -> list of distinct normalised words.
- `save_filter(filter, path)` / `load_filter(path)` — the
  `CCBF` file format above; `load_filter` rejects a bad
  magic, an unsupported version, or a truncated file with
  `ValueError`.
- `check_words(filter, words)` -> list of words probably
  spelt wrong, in input order (duplicates preserved).

## Explicitly NOT built

- Spelling suggestions / corrections. The page does not ask
  for them (that is the separate Spelling Correction
  challenge). A Bloom filter stores no words, so it cannot
  suggest a correction; adding suggestions would require a
  second, stored word list, which defeats the point.
- The "common passwords" going-further idea.
- Downloading a dictionary: tests use small synthetic
  dictionaries only (see TEST_PLAN.md); a real dictionary
  file is supplied by the user at build time.
