# password-cracker — SPEC

Source: Coding Challenges, "Build Your Own Password Cracker",
page slug `challenge-password-cracker`
(`https://codingchallenges.fyi/challenges/challenge-password-cracker/`).
First-guess slug, no 404, no correction needed. Built from the
page's steps, not from memory.

## Challenge steps implemented

- Step 0: setup only (Python 3, standard library only).
- Step 1: MD5 implemented by hand (RFC 1321 algorithm, in
  `cracker.py:md5_hex`), verified against `hashlib.md5`.
  The page allows using the language's hash functions; the
  hand implementation is kept because the step's stated goal
  is awareness of how password hashes are generated.
- Step 2: brute force — generate every permutation of a
  character set up to a given length, hash each candidate,
  compare to a target hash (John the Ripper "incremental
  mode" equivalent).
- Step 3: dictionary attack — read a user-supplied wordlist
  file, hash each word, compare to the target. The user
  chooses `--mode dict` or `--mode brute` and, for dict
  mode, supplies `--wordlist PATH`.
- Step 4: build a rainbow table — pre-compute hashes for a
  wordlist and/or generated candidates and save
  `hash<TAB>password` lines to a file.
- Step 5: crack from a rainbow table — load the file and
  look the target hash up in it.
- Step 6 (bonus): other hash functions (SHA-1, SHA-256,
  SHA-512 via `hashlib`) and salting (a salt prepended or
  appended to the candidate before hashing). The page also
  asks to read up on key derivation functions (KDFs); see
  the security note in DESIGN.md — no KDF-based cracking
  mode is implemented, because fast unsalted hashes are
  exactly the insecure storage this challenge demonstrates.

## Interface

Library functions in `cracker.py` (all pure, testable):

- `md5_hex(data: bytes) -> str` — hand-rolled MD5 hex digest.
- `hash_password(password, algo="md5", salt="", salt_position="prefix") -> str`
  — hex digest for `algo` in `md5 | sha1 | sha256 | sha512`.
  `salt_position` is `prefix`, `suffix`, or `none` (ignored
  when `salt` is empty).
- `dictionary_attack(target, words, algo=..., salt=..., salt_position=...)`
  -> `(password_or_None, attempts)`.
- `brute_force_attack(target, charset, min_length, max_length, ...)`
  -> `(password_or_None, attempts)`. Candidates are generated
  in length order, then in charset order (`itertools.product`).
- `build_rainbow_table(passwords, algo=..., salt=..., salt_position=...)`
  -> `dict[hash, password]` (first password wins on collision).
- `write_rainbow_table(path, table)`, `load_rainbow_table(path)`
  — file format is one `hash<TAB>password` line per entry.
- `crack(target, mode, ...)` — dispatcher over `dict`,
  `brute`, and `rainbow` modes.

CLI (see README.md for examples):

```
python3 cracker.py hash TARGET --algo md5 --mode brute \
    --charset-preset lower --min-length 1 --max-length 4
python3 cracker.py hash TARGET --mode dict --wordlist words.txt
python3 cracker.py build-table --wordlist words.txt --output table.txt
python3 cracker.py build-table --charset-preset lower \
    --min-length 1 --max-length 3 --output table.txt
python3 cracker.py lookup TARGET --table table.txt
```

Exit code 0 prints `Password found: <password>`; exit code 1
prints `Password not found` (both also report attempts where
applicable). Bad arguments / unknown algorithm / unreadable
files / invalid ranges go to stderr with exit code 2
(argparse) or a clear `ValueError` from the library.

## Input rules / errors

- Target hashes are compared case-insensitively (lowercased)
  and stripped of surrounding whitespace.
- Unknown `algo` -> `ValueError`. Unknown `salt_position`
  -> `ValueError`. Empty charset -> `ValueError`.
  `min_length < 1`, `max_length < min_length` -> `ValueError`.
- Dictionary files: one candidate per line, trailing `\n` /
  `\r\n` stripped, blank lines skipped, other whitespace kept.
- Rainbow-table files: lines without a tab, or with an empty
  hash, are skipped on load (not an error); the first entry
  wins for a duplicated hash.

## Scope and safety (binding)

EDUCATIONAL USE ONLY, on hashes you generate yourself
(e.g. hashes of passwords you invented for a test, or of
your own account's password in a system you control and are
authorised to test). Never use this tool on hashes belonging
to anyone else, on leaked password lists, or on a live system
without explicit authorisation. No wordlist is downloaded or
bundled: tests create tiny synthetic wordlists in temporary
directories at run time, and the page's suggested external
wordlist is deliberately NOT fetched. See README.md.
