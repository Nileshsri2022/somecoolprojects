# zip-file-cracker — TEST_PLAN

Run from the project directory:

```
python3 -m unittest discover -s tests -v
```

## Fixtures: synthetic ZipCrypto zips, made in the test run

No fixture file is checked in and no real protected archive is
used. `tests/test_cracker.py` contains a minimal ZipCrypto
writer (`_write_encrypted_zip`, stored method, 12-byte
encryption header whose last byte is the CRC high byte — the
form stdlib `zipfile` validates). It is the exact inverse of
`zipfile._ZipDecrypter`: same initial keys, same CRC table,
same key-update. Every test zip is created in a `tempfile`
directory with a short synthetic password (`test`, `ab`, …)
and short synthetic content, then deleted with the directory.

Sanity of the writer itself is tested first: stdlib reads the
fixture with the right password and raises `RuntimeError` with
the wrong one. If that sanity test fails, every attack test
built on the writer is untrustworthy, so it runs first in
file order and the rest depend on the same helper.

## Coverage (each maps to a page step)

Step 1 — header check:
- zip fixture has headers; a plain text file does not; an
  empty file does not; a missing file does not (no exception).
- header-only CLI prints exactly `Has zip headers.` /
  `Does not have zip headers.` with exit 0 / 1.

Step 2 — dictionary:
- password present in the middle of a synthetic wordlist is
  found, with the exact attempt count (position in the list).
- password absent returns `(None, len(wordlist))`.
- blank lines are skipped and not counted.
- wordlist file missing raises `FileNotFoundError` from the
  library function and exit 2 from the CLI.
- CLI `-dict` without `--wordlist` exits 2 (documented
  divergence: no bundled/downloaded wordlist).

Step 3 — brute force:
- `test` found with charset `test` (or `lower`), min 1 max 4,
  with the exact attempt count for the single-worker search.
- absent password within the bounded space returns
  `(None, total_candidates)`.
- invalid ranges / empty charset raise `ValueError`.
- `--max-attempts` stops the search early.

Step 4 — concurrency:
- dictionary attack with `workers=4` still finds the password
  (attempt count asserted only as `>=` the single-worker
  position, since parallel batches dispatch extra candidates).
- CLI default workers equals `os.cpu_count()` (asserted via
  the parsed default, not by timing).

Guards / divergences:
- unencrypted zip: `try_password` is `False` for any password
  (no false positive), and a dictionary attack returns not
  found.
- AES marker: a zip whose member has `compress_type == 99`
  raises `UnsupportedEncryptionError` from the attack
  functions (constructed in-test by patching the central
  directory entry's method byte — no real AES file needed).
- empty archive: attack raises `ValueError`.
- unknown `--member`: attack raises `ValueError`.
- nested detection: decrypted content that itself starts with
  `PK\x03\x04` is reported by `looks_like_zip()`; content
  that does not is not.
- CLI end-to-end: `-dict` and `-brute` runs against a
  fixture print `Password found: <password>` and exit 0;
  a failed search prints `Password not found.` and exits 1.

## Non-goals

- No timing / performance benchmarks (ZipCrypto attempt speed
  is environment-dependent and irrelevant to correctness).
- No test against a real AES-encrypted zip (stdlib cannot
  decrypt one; the marker test above covers the code path).
- No downloaded or bundled wordlist is ever read by tests.
