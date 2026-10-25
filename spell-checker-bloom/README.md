# spell-checker-bloom — Build Your Own Spell Checker Using A Bloom Filter

Coding Challenge #53, worked in `somecoolprojects/` (entry 41).
Docs first, then code — see `docs/`.

A Bloom filter spell checker: it stores no words, only a bit
array. A word it reports absent is definitely misspelt; a word
it reports present is only *probably* spelt correctly (false
positives are possible, false negatives are not).

## Usage

Build a filter from a dictionary file:

```sh
python3 spell_checker.py -build dict.txt [words.bf]
python3 spell_checker.py -build dict.txt -o words.bf --fp-rate 0.01
```

Check words against a saved filter (page's example words):

```sh
python3 spell_checker.py words.bf hi hello word concurrency coding challenges imadethis up
These words are spelt wrong:
 coding
 challenges
 imadethis
```

(The three "wrong" words are simply absent from the dictionary
used — exactly as on the challenge page.)

The saved file uses the page's format: magic `CCBF`, version 1,
hash count, and bit count (all big-endian), then the bit array.
Hashing is FNV-1a + FNV-1 with double hashing; sizing follows
the standard formulas (`m = -n ln p / (ln 2)^2`,
`k = (m/n) ln 2`). See `docs/DESIGN.md`.

No spelling suggestions: a Bloom filter stores no words, so it
cannot suggest corrections — that is the separate Spelling
Correction challenge.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use small synthetic dictionaries only (no downloads) and
verify no false negatives, bounded measured false-positive
rate on held-out words, byte-exact `CCBF` round-trips with
corrupt-header rejection, and CLI build + check end-to-end.

## Page slug caveat

The codingchallenges.fyi slugs `challenge-spell-checker/` and
`challenge-bloom-filter/` both returned 404, so this build is
taken from the challenge's canonical Challenge #53 text on
Substack (same title, steps, and file format). See
`docs/SPEC.md` for details.
