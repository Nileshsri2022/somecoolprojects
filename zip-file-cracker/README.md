# zip-file-cracker — Build Your Own Zip File Cracker

Coding Challenge #66, from
https://codingchallenges.fyi/challenges/challenge-zip-cracker/
(see `docs/SPEC.md` for the slug correction: `challenge-zip-file-cracker`
404s; the live slug is `challenge-zip-cracker`).

Python 3 standard library only. Single main file: `cracker.py`.

## Educational scope — read this first

Use this tool ONLY on zip files you created yourself, or archives
you are explicitly authorised to test. The point of the challenge
— the page's own lesson — is that a ZipCrypto archive with a weak
password is not real protection for personal or sensitive data:
never use a password-protected zip to share such data.

No wordlist is bundled and none is downloaded. For a dictionary
attack you supply your own `--wordlist` file; the tests generate
tiny synthetic wordlists and synthetic encrypted zips inside the
test run. Never run this against someone else's archive, a leaked
password list, or a live system without authorisation.

## Usage

Header check only (Step 1, page's exact output):

```sh
python3 cracker.py cctest.zip
# Has zip headers.
python3 cracker.py cc.txt
# Does not have zip headers.
```

Dictionary attack (Step 2 — supply your own wordlist):

```sh
printf 'alpha\ntest\n' > words.txt
python3 cracker.py -dict cctest.zip --wordlist words.txt
# Password found: test
```

Brute force (Step 3 — page's example range, restricted charset
shown so the example finishes quickly; default charset is `a-z`):

```sh
python3 cracker.py -brute -min=1 -max=4 cctest.zip --charset test
# Password found: test
```

Both, dictionary first (Step 2 before Step 3, as the page
recommends), and concurrency (Step 4: one worker per CPU core
by default, `--workers` overrides):

```sh
python3 cracker.py -dict -brute cctest.zip --wordlist words.txt --workers 4
```

Other options: `--charset-preset lower|upper|digits|alpha|alnum`,
`--member <name>` (default: first member), `--max-attempts N`.

Exit codes: 0 = headers present / password found; 1 = headers
absent / password not found; 2 = error (missing file, missing
`--wordlist` for `-dict`, invalid range, unsupported encryption).

## Limitations (documented, not hidden)

- Only traditional ZipCrypto archives are crackable: Python's
  stdlib `zipfile` cannot decrypt AES-encrypted zips (method 99)
  and cannot create encrypted zips. AES archives are rejected
  up front with a clear error.
- An unencrypted archive never "matches" a password — it needs
  none, so reporting a match would be a false positive.
- Going Further is partial: after a successful crack the tool
  notes when the decrypted content is itself a zip, but does not
  recursively crack a nested archive. See `docs/DESIGN.md`.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use only synthetic zips created in the test run (a small
ZipCrypto writer in the test file, verified against stdlib
decryption) and synthetic wordlists. See `docs/TEST_PLAN.md`.
