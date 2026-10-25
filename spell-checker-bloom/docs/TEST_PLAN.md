# TEST_PLAN — Spell Checker Using A Bloom Filter

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

All tests use small synthetic dictionaries written inline or
to temp files. No dictionary is downloaded, and no test
depends on `/usr/share/dict/words` existing.

## Cases

1. Sizing (`optimal_parameters`):
   - `n=1000, p=0.01` -> 9586 bits, 7 hashes (the standard
     formula values).
   - Larger `n` / smaller `p` grow `m`; `k >= 1` always.
   - `n <= 0`, `p <= 0`, `p >= 1` raise `ValueError`.
   - The theoretical rate of the returned parameters is at
     or below the target (within rounding slack).
2. Hashing:
   - FNV-1a-64 of `""` is the offset basis
     `0xcbf29ce484222325`; of `"a"` is
     `0xaf63dc4c8601ec8c` (published test vectors).
   - Hash positions are always in `[0, m)`, and two
     different words do not always collide (sanity).
3. Membership / no false negatives:
   - Insert a synthetic dictionary (~50 words); every one
     is reported present.
   - `add` is idempotent: re-adding changes nothing.
   - An empty word raises `ValueError` on `add` and is
     reported absent by `__contains__` (never silently
     inserted as a bit pattern).
   - Case-insensitivity: `Hello` is present after adding
     `hello`.
4. False-positive behaviour (held-out words):
   - Build a filter from a synthetic dictionary at target
     rate 0.01; check 1,000 held-out words that share no
     string with the dictionary. Assert the measured rate
     is below 0.10 (a loose bound: the target is 0.01, but
     a single deterministic sample can vary; 0.10 catches a
     broken hash/bit layout while not flaking on sampling
     noise) and report the measured rate in the test name
     output via the assertion message.
   - A deliberately tiny, saturated filter (few bits, many
     words) shows a strictly positive false-positive rate,
     demonstrating the probabilistic behaviour is real and
     not masked by an over-large test filter.
5. File format round-trip:
   - `save_filter` output starts with `b"CCBF"`, version 1
     big-endian, the hash count, and the bit count, and its
     total length is `12 + ceil(m / 8)` bytes.
   - `load_filter` of a saved file reproduces membership
     exactly (inserted words present, and the same held-out
     word verdicts).
   - Corrupt files raise `ValueError`: bad magic, version 2,
     zero hashes, zero bits, truncated bit array, trailing
     garbage.
6. Dictionary loading:
   - Blank lines skipped, words lowercased, duplicates
     collapsed to one entry, order of first appearance kept.
7. CLI end-to-end (subprocess, temp directory):
   - `-build` on a synthetic dictionary creates `words.bf`
     and prints the word/bit/hash counts.
   - Check mode with the page's example words
     (`hi hello word concurrency coding challenges imadethis
     up`, dictionary containing the first four plus `up`)
     prints exactly:
     ```
     These words are spelt wrong:
      coding
      challenges
      imadethis
     ```
   - Check mode with all-correct words prints nothing.
   - Bad usage (no arguments, missing dictionary file,
     missing filter file) exits non-zero with usage/a
     diagnostic on stderr.

## What is NOT tested

- Performance on a real 100k-word dictionary (no such file
  is bundled; the formulas and byte layout are the same at
  any scale, and a user can verify size with `du` as the
  page does).
- Spelling suggestions: not a feature (see SPEC.md).
