# password-cracker — TEST_PLAN

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

All tests use ONLY hashes generated inside the test run
(`hashlib` / the tool's own functions, over synthetic
passwords invented for the test, e.g. `apple`, `zz`,
`Ab3`). No real passwords, no leaked lists, no downloaded
wordlists, no page example hashes. Wordlists and tables
are created in `tempfile.TemporaryDirectory` and deleted
afterwards.

## Cases (in `tests/test_cracker.py`)

MD5 (Step 1):
- Hand MD5 equals `hashlib.md5` for: empty input, `a`,
  `abc`, 55/56/63/64/65-byte inputs (padding/block
  boundaries), a 1000-byte input, and non-ASCII UTF-8.
- `md5_hex` returns a 32-char lowercase hex string.
- Known-vector sanity: hand MD5 of `abc` is checked
  against `hashlib` (not a hardcoded external vector).

Hashing / salting (Step 6):
- `hash_password` matches `hashlib` for md5/sha1/sha256/
  sha512 on the same input.
- Salt prefix vs suffix give different digests, both
  differ from unsalted, and both are reproducible.
- Unknown algorithm / unknown salt position raise
  `ValueError`; target normalisation (case/whitespace)
  is tested via `crack`.

Dictionary attack (Step 3):
- Finds a word in the middle of a synthetic wordlist,
  with the correct attempt count (position in file).
- Returns `(None, len(words))` when absent; blank lines
  in the file are skipped (not counted as attempts).
- Works with sha256, not just md5.
- Salted target found only with the matching salt.

Brute force (Step 2):
- Finds a 2-char password over a tiny charset, with the
  exact attempt count for length-then-charset ordering.
- Finds a 1-char password; respects `min_length`
  (a password shorter than `min_length` is not found).
- Returns `(None, total_candidates)` when absent.
- `max_attempts` stops early with the capped count.
- Invalid charset / length range raises `ValueError`
  (empty charset, min < 1, max < min).

Rainbow table (Steps 4–5):
- `build_rainbow_table` maps every synthetic password to
  its hash; round-trip through `write`/`load` preserves
  the mapping; first password wins on a hash collision
  (forced via a duplicate entry).
- `lookup` via `crack(mode="rainbow")` finds a present
  hash and misses an absent one; malformed table lines
  (no tab, empty hash) are skipped on load.
- A table built from generated brute-force candidates
  cracks a short password (end-to-end Step 4 -> 5).

CLI:
- `hash` subcommand finds (exit 0, `Password found: X`)
  and misses (exit 1, `Password not found`) for dict and
  brute modes; `build-table` writes a loadable file;
  `lookup` finds a tabled hash; bad algorithm exits
  non-zero with an error on stderr.
- CLI tests invoke `main(argv)` in-process (no shelling
  out) and capture stdout/stderr.

## Success criteria

Every test passes; hand MD5 agrees with `hashlib` on all
boundary inputs; every attack mode finds a synthetic
password it should find and honestly reports not-found
otherwise. Brute-force tests keep charsets/lengths tiny
so the suite runs in seconds.
