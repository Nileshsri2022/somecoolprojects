# zip-file-cracker — DESIGN

Assumptions, stated before coding (ponytail: think first,
minimum code, nothing speculative).

## Pipeline

```
path -> has_zip_headers()          (Step 1: first 4 bytes)
     -> describe target member     (first member, or --member)
     -> reject AES / empty / plain (up front, not per candidate)
     -> candidates (wordlist lines, or itertools.product)
     -> try_password() per candidate
          ZipFile(path).read(member, pwd=...)   # stdlib ZipCrypto
          success = bytes returned; wrong pwd raises RuntimeError
     -> found password + attempts, or None + attempts
```

One attempt core, `try_password()`, serves dictionary, brute
force, and both-modes. Only the candidate source differs. That
keeps the bug surface in one place.

## Header check (Step 1)

The first four bytes are compared against the zip signatures
`PK\x03\x04` (local file header, the page's example),
`PK\x05\x06` (empty archive / end of central directory) and
`PK\x07\x08` (spanned archive marker). A file shorter than
four bytes, or unreadable, does not have zip headers. No other
parsing is attempted in header mode — the page asks only for
the header verdict.

## Attempt semantics

- `try_password(path, password, member=None)` returns `True`
  only when stdlib decryption of an encrypted member succeeds.
  Wrong passwords raise `RuntimeError: Bad password` inside
  `zipfile`; that is caught and becomes `False`. A corrupted
  archive (`BadZipFile`) is also `False` for a single attempt —
  the caller decides whether to keep trying.
- Unencrypted member: returns `False` for every password. A
  plain zip needs no password, so reporting any candidate as
  "found" would be a false positive.
- AES member (`compress_type == 99`): `try_password` raises
  `UnsupportedEncryptionError`. The attack functions check this
  once, before the loop, so an AES archive fails fast with one
  clear message instead of one misleading failure per candidate.
- Empty archive: attack functions raise `ValueError` before
  the loop (there is nothing to decrypt).
- Member selection: default is the first member in central
  directory order; `--member` / `member=` selects by name and
  raises `ValueError` for an unknown name.

## Dictionary attack (Step 2)

The wordlist is streamed line by line (never loaded whole),
each line stripped of only `\r\n` / `\n`. Blank lines are
skipped without counting as attempts. Candidates are tried in
file order; the first success stops the search and its attempt
count is exact in single-worker mode.

## Brute force (Step 3)

`itertools.product(charset, repeat=length)` for
`length` in `min_length .. max_length` inclusive, shortest
first, in charset order. The charset is de-duplicated preserving
order. Validation up front: non-empty charset, `1 <= min <= max`.
`--max-attempts` bounds any search (dictionary or brute force);
hitting the bound without success returns `(None, attempts)`.

## Concurrency (Step 4)

The CLI defaults to one worker per CPU core
(`os.cpu_count() or 1`), as the page specifies. Each worker
opens its own `ZipFile` per attempt — `ZipFile` objects are
not shared across threads. Candidates are dispatched in
batches of `workers * 4`; a batch is fully evaluated before
the next is dispatched, so the search still stops promptly
after the batch containing the hit. Reported attempts in
parallel mode count every candidate dispatched in completed
batches (including the rest of the hit's batch), not the exact
position of the hit — exact position is only meaningful
single-threaded, and the library default (1 worker) keeps
tests deterministic.

## Nested zip (Going Further, partial)

After a successful crack, the CLI reads the decrypted first
member and runs `has_zip_headers()` over its bytes. If it
looks like a zip, it prints a note saying so. It does not
recursively crack it: a nested archive needs its own member
selection and password search, and the page presents this as
an optional extension ("You could take this further"), not a
required step. This keeps the tool honest about its scope.

## Educational scope

This tool exists to demonstrate, on zip files you create
yourself, why ZipCrypto with a weak password is not real
protection — the page's own stated lesson. Use it only on
archives you created or are authorised to test. It ships no
wordlist and downloads none: the page's CrackStation
suggestion is deliberately NOT followed, per the task
constraint (synthetic wordlists only, generated in tests).
