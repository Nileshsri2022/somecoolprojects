# password-cracker — Build Your Own Password Cracker

Coding Challenges #40, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A teaching password cracker: hand-rolled MD5, brute-force
attack, dictionary attack, rainbow-table build/lookup, and
bonus SHA-1/SHA-256/SHA-512 plus salting. Python 3 standard
library only.

## Educational scope — read this first

Use this tool ONLY on hashes you generated yourself — for
example, hashes of passwords you invented to test with, or
of your own password in a system you control and are
authorised to test. Never run it against hashes belonging
to anyone else, against leaked password lists, or against
a live system without explicit authorisation. No wordlist
is downloaded or bundled: you supply your own file, and
the tests generate tiny synthetic wordlists at run time.
The point of the challenge is the lesson, not the weapon:
fast unsalted hashes (MD5, SHA-1) are insecure password
storage. Real systems must use a slow, salted KDF designed
for passwords (Argon2id, bcrypt, scrypt).

## Usage

Brute force (Step 2) — crack a hash you made yourself:

```sh
python3 -c "from hashlib import md5; print(md5(b'ab').hexdigest())"
# 187ef4436122d1cc2f40dc2b92f0eba0
python3 cracker.py hash 187ef4436122d1cc2f40dc2b92f0eba0 \
    --mode brute --charset-preset lower --min-length 1 --max-length 2
# Password found: ab (after 28 attempts)
```

Dictionary attack (Step 3) — supply your own wordlist:

```sh
printf 'alpha\nbeta\ngamma\n' > /tmp/words.txt
python3 cracker.py hash <md5-of-beta> --mode dict --wordlist /tmp/words.txt
# Password found: beta (after 2 attempts)
```

Rainbow table (Steps 4–5):

```sh
python3 cracker.py build-table --wordlist /tmp/words.txt --output /tmp/table.txt
# Wrote 3 entries to /tmp/table.txt
python3 cracker.py lookup <md5-of-gamma> --table /tmp/table.txt
# Password found: gamma
```

Other hashes and salting (Step 6):

```sh
python3 cracker.py hash <sha256-hash> --algo sha256 \
    --mode brute --charset ab --min-length 1 --max-length 2
python3 cracker.py hash <salted-hash> --salt pep --salt-position suffix \
    --mode dict --wordlist /tmp/words.txt
```

`--charset` takes a raw string and overrides
`--charset-preset` (`lower`, `upper`, `digits`, `alpha`,
`alnum`). `--max-attempts` bounds a search. Exit code 0
means found, 1 means not found, 2 means an error (bad
arguments, unreadable file, invalid range).

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover every challenge step, MD5 against `hashlib`
at padding/block boundaries, salting, attempt counts,
rainbow-table round-trips, and the CLI. Every target hash
is generated inside the test run from a synthetic password;
no real passwords, leaked lists, downloaded wordlists, or
challenge example hashes appear anywhere in this project.

## Files

- `cracker.py` — hand-rolled MD5, hashing/salting, dict /
  brute / rainbow attacks, CLI.
- `docs/SPEC.md` — challenge spec and interface.
- `docs/DESIGN.md` — assumptions, MD5 design, and
  documented divergences from the page.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_cracker.py` — the test suite.
