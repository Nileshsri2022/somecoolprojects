# password-cracker — DESIGN

Assumptions, stated before coding (ponytail: think first,
minimum code, nothing speculative).

## Pipeline

```
candidate password
  -> apply salt (prefix / suffix / none)
  -> encode UTF-8
  -> hash (hand MD5, or hashlib for sha1/sha256/sha512)
  -> hex digest, lowercased
  -> compare to target hash
```

One comparison core, `hash_password()`, serves every attack
mode. Dictionary, brute force, and rainbow-table building
only differ in where candidates come from; lookup only
differs in that the hashes are pre-computed. That keeps the
attack surface of the code (and its bugs) in one place.

## Hand-rolled MD5 (Step 1)

Standard RFC 1321 MD5: little-endian words, the four rounds
(F, G, H, I) with the fixed per-round shift amounts and the
`floor(abs(sin(i)) * 2**32)` constant table, padding with
`0x80` + zeroes + 64-bit little-endian bit length, and the
initial state `0x67452301, 0xefcdab89, 0x98badcfe,
0x10325476`. It is written from the algorithm, not copied
from a library, and verified exhaustively against
`hashlib.md5` in tests (empty string, single bytes, block
boundaries at 55/56/64 bytes, long inputs). MD5 is used
because the challenge specifies it; MD5 is broken for
security purposes and must never be used to store real
passwords — that insecurity is the point of the challenge.

## Other hashes and salting (Step 6)

SHA-1 / SHA-256 / SHA-512 go through `hashlib`, not through
hand implementations: re-implementing four more hashes adds
code and bug surface for no new concept, and the page
explicitly allows using the language's hash functions.
Salting is modelled minimally: one salt string, prepended
or appended. This demonstrates why salting defeats a plain
rainbow table (the table must be rebuilt per salt) without
pretending to be a production password store.

Security note (from the page's Step 6 reading): real systems
should store passwords with a slow, salted KDF designed for
passwords (e.g. Argon2id, bcrypt, scrypt) — never a fast
unsalted hash like MD5/SHA-1. This tool cracks fast hashes
to teach that lesson; it is not a password-storage library
and ships no storage code at all.

## Attack modes

- Dictionary: iterate the wordlist in file order, count
  attempts, stop at the first match. File order is the
  attack order; no sorting, no deduplication (a duplicate
  word costs one extra attempt, exactly as in real tools).
- Brute force: `itertools.product(charset, repeat=length)`
  for `length` in `min_length..max_length`, in that order.
  Charset presets: `lower` (a-z), `upper` (A-Z),
  `digits` (0-9), `alpha` (a-zA-Z), `alnum` (a-zA-Z0-9).
  A raw `--charset` string overrides the preset. Candidates
  are generated lazily, never materialised as a list, so a
  large search costs time, not memory.
- Rainbow table: a plain `dict` in memory, serialised as
  `hash<TAB>password`. This is the page's Step 4/5 literally
  (a pre-computed hash->password file), not a true rainbow
  table with reduction functions and chains — the page
  describes the simplified form ("save that hash and the
  input 'password' used to generate the hash to a file"),
  and the simplified form is what is built and documented
  as such (see Divergences).
- Optional `max_attempts` on dictionary/brute attacks stops
  the search early and returns `(None, attempts_so_far)`;
  it exists so a runaway brute force can be bounded in
  tests and by users. The CLI exposes it as
  `--max-attempts`.

## Divergences from the page (all deliberate, documented)

1. No external wordlist download. The page suggests
   CrackStation's Smaller Wordlist; per the project brief
   no external wordlist is fetched or bundled. Users supply
   their own file; tests generate synthetic ones.
2. Simplified rainbow table (hash->password map), not
   chained rainbow tables with reduction functions — this
   is what Steps 4–5 describe, and chaining would be
   speculative extra machinery.
3. No multithreading / GPU path (page: "Going Further").
   Single-threaded, standard library only. Parallelism
   would complicate the code for a teaching tool whose
   searches are deliberately tiny.
4. No KDF cracking mode, no salted-rainbow-table builder
   beyond the `salt` parameters on `hash_password` /
   `build_rainbow_table` (a salted table is just a table
   built with a salt).
5. The page's example target hashes are not reproduced in
   code, tests, or docs: tests hash synthetic passwords
   created inside the test run, so nothing in this project
   depends on (or leaks) any external password example.
6. Minimum brute-force length is 1 (the empty password is
   not a candidate). This is a stated boundary, not a
   page requirement — the page says "up to a certain
   length" without fixing a minimum.

## Errors

Library functions raise `ValueError` for bad algorithm,
salt position, charset, or length range, and let file I/O
errors (`OSError`) propagate unchanged — the CLI reports
them and exits non-zero. No exception is swallowed into a
"not found" result: a failed read is not a failed crack.
