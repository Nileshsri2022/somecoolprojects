# zip-file-cracker — SPEC

Source page: https://codingchallenges.fyi/challenges/challenge-zip-cracker/
(Coding Challenge #66, "Build Your Own Zip File Cracker".)

Slug note: the first guess `challenge-zip-file-cracker` 404s on
codingchallenges.fyi. The correct slug is `challenge-zip-cracker`
(confirmed live 2026-10-25); the Substack original is
https://codingchallenges.substack.com/p/coding-challenge-66-zip-file-cracker

## Steps, as specified on the page

- Step 0 — Set up. Create a test zip with `zip -e cctest.zip cc.txt`
  and password `test` (page's example). This build instead creates
  its test zips inside the test run (see TEST_PLAN.md); no external
  fixture is checked in.
- Step 1 — Verify the file is a zip file by checking its headers.
  Behaviour required by the page:
  ```
  % cczipcrack cctest.zip
  Has zip headers.
  % cczipcrack cc.txt
  Does not have zip headers.
  ```
  The page's hex dump starts `504b 0304` (`PK\x03\x04`, the local
  file header signature). Metadata is not encrypted, so the member
  name (`cc.txt`) is visible even in an encrypted archive.
- Step 2 — Dictionary attack. Try every word in a wordlist against
  the zip; print the correct password when found. The page suggests
  the CrackStation Smaller Wordlist and allows using a library for
  zip encryption instead of implementing the spec by hand.
  ```
  % cczipcrack -dict cctest.zip
  Password found: test
  ```
- Step 3 — Brute-force attack. Try all combinations of allowable
  characters between a user-specified min and max length.
  ```
  % cczipcrack -brute -min=1 -max=4 cctest.zip
  Password found: test
  ```
- Step 4 — Check concurrently: one thread per CPU core.
- Going Further — If the decrypted contents are themselves an
  encrypted zip, crack that too.

## What this build implements

| Page step | Implemented |
|---|---|
| Step 1 header check | Yes: `has_zip_headers()` + header-only CLI mode, printing exactly the page's two messages. |
| Step 2 dictionary attack | Yes: `dictionary_attack()`, CLI `-dict` / `--dict`. |
| Step 3 brute force | Yes: `brute_force_attack()`, CLI `-brute` / `--brute`, `-min` / `-max`. |
| Step 4 concurrency | Yes: `ThreadPoolExecutor` with one worker per CPU core by default in the CLI (`--workers` overrides); library functions default to 1 worker for deterministic attempt counts. |
| Going Further (nested zip) | Partially: after a successful crack, the CLI reports when the decrypted first member itself has zip headers. It does NOT recursively crack a nested archive (see Divergences). |

## CLI contract

```
python3 cracker.py <zipfile>                    # header check only
python3 cracker.py -dict <zipfile> --wordlist <file>
python3 cracker.py -brute -min=1 -max=4 <zipfile> [--charset abc]
python3 cracker.py -dict -brute <zipfile> --wordlist <file>   # dict first, brute if dict fails
```

- Exit 0: headers present (header mode) or password found.
- Exit 1: headers absent, or password not found after the search.
- Exit 2: usage / I/O error (missing file, missing `--wordlist` for
  `-dict`, invalid min/max/charset, unsupported encryption).
- A password attempt succeeds only for an actually encrypted
  member: an unencrypted archive never "matches" any password
  (otherwise every password would trivially "succeed").
- Passwords are encoded as UTF-8 bytes for `zipfile`.
- Dictionary lines have only the trailing `\r\n` / `\n` stripped;
  blank lines are skipped and not counted as attempts.
- Brute-force default charset is lowercase letters (`a-z`), the
  charset that finds the page's example password `test`; `--charset`
  overrides it, `--charset-preset` selects
  `lower` / `upper` / `digits` / `alpha` / `alnum`.

## Encryption scope (stdlib limitation)

Python's stdlib `zipfile` decrypts traditional ZipCrypto only.
It cannot decrypt AES-encrypted zips (compression method 99), and
it cannot create encrypted zips at all. Consequences, all
documented rather than hidden:

- AES-encrypted archives are detected up front and rejected with
  a clear error ("AES-encrypted zip files are not supported by
  Python's stdlib zipfile"), instead of failing silently on every
  candidate.
- Test fixtures are therefore created inside the test run by a
  small ZipCrypto writer in the test file itself (the inverse of
  `zipfile._ZipDecrypter`'s algorithm, stored method, no
  compression), verified against stdlib decryption. The main
  program contains no encryption code and no fixture files.
