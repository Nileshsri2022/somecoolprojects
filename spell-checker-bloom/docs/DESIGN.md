# DESIGN — Spell Checker Using A Bloom Filter

## Assumptions (stated before coding, ponytail rules)

1. The challenge is about membership testing, not correction:
   the only question the program answers is "probably in the
   dictionary / definitely not". No correction, no ranking.
2. Words are case-insensitive. Dictionary words and checked
   words are both lowercased, so `Hello` matches `hello`.
   No stemming, no punctuation stripping beyond whitespace:
   a checked word is taken as typed (after lowercasing).
   This keeps the filter's contract exact: membership is
   membership of the normalised string.
3. The dictionary fits in memory as a list of strings while
   building. The page's point is that the *saved* filter is
   small; building still reads the dictionary once. Sizing
   uses the distinct-word count, so duplicates do not inflate
   the filter (inflating it would only lower the real
   false-positive rate at the cost of size — harmless but
   wasteful, and it would make the size formula lie).
4. One file, stdlib only, no third-party hash library.

## Sizing formulas (standard Bloom filter formulas)

For expected items `n` and target false-positive rate `p`:

```
m = ceil(-n * ln(p) / (ln 2)^2)        # bits
k = round((m / n) * ln 2)              # hash functions, >= 1
```

Theoretical false-positive rate for a filter with `m` bits,
`k` hashes, `n` items inserted:

```
p ≈ (1 - exp(-k * n / m)) ^ k
```

Sanity check: `n = 1000, p = 0.01` gives `m = 9586` bits
(~1.2 KB) and `k = 7`. The page's example header
(`0x003d0900` = 4,000,000 bits, `k = 4`) is consistent with
a larger dictionary at a looser target rate; it is not
reproduced exactly because it depends on the author's
dictionary size and chosen rate, which the page does not
state.

Edge cases: `n <= 0` or `p` outside `(0, 1)` raises
`ValueError`. `k` is clamped to at least 1 and `m` to at
least 1, so a one-word dictionary still yields a usable
filter.

## Hashing: FNV-1a + FNV-1, double hashing

The page suggests Fowler-Noll-Vo. Two independent 64-bit
variants are implemented by hand (no `hashlib` dependence
for the core, and no reliance on Python's salted `hash()`):

- `h1 = FNV-1a-64(word)` — xor then multiply per byte.
- `h2 = FNV-1-64(word)` — multiply then xor per byte.

Both use the standard 64-bit offset basis
`0xcbf29ce484222325` and prime `0x100000001b3`, masked to
64 bits. Positions for hash `i` (0-based) are:

```
(h1 + i * h2) mod m
```

This is Kirsch-Mitzenmacher double hashing: two hashes
simulate `k` hashes, and it needs no `k` separate hash
functions. `h2` is forced odd (and non-zero): if the raw
`h2` is even, `h2 |= 1`. Without that, an even step could
never reach half the bit positions when `m` is a power of
two, and could cycle through a small subset in general.
Forcing oddness costs nothing (it only perturbs one hash
value) and guarantees the step is coprime to any `m`.

Why not `hashlib` digests sliced into `k` pieces? That
would also work, but FNV is what the page suggests, it is
~15 lines, and it keeps the hash behaviour identical on
every Python build (unlike salted `hash()`).

## Bit array

A `bytearray` of `ceil(m / 8)` bytes; bit `i` is byte
`i // 8`, bit `i % 8` (least-significant-bit first within
each byte). No bit is ever cleared, so false negatives are
impossible by construction: every inserted word has all
its `k` bits set, and they stay set.

## File format (page-exact)

```
offset  size  field
0       4     b"CCBF"
4       2     version = 1, big-endian unsigned
6       2     num_hashes, big-endian unsigned
8       4     num_bits, big-endian unsigned
12      ...   bit array, ceil(num_bits / 8) bytes
```

`load_filter` validates, in order: file at least 12 bytes,
magic `CCBF`, version 1, `num_hashes >= 1`,
`num_bits >= 1`, and the bit array present in full
(short files and trailing-garbage files both raise
`ValueError` — trailing bytes are rejected rather than
ignored, so a corrupt/concatenated file cannot silently
pass). The in-memory bit array is truncated to exactly
`num_bits` on load (padding bits in the last byte are
ignored on read, and are always written as zero).

## CLI shape

Two modes, matching the page's two commands:

- `-build dict.txt [output]` — the page's
  `ccspellcheck -build dict.txt`. Optional `-o` output
  and `--fp-rate` (default 0.01). Building prints a one-line
  summary to stdout: words loaded, bits, hashes, file.
- `<filter.bf> word...` — the page's check mode. The first
  argument must name an existing `.bf` file; anything else
  is a usage error. Checked words keep input order in the
  wrong-word listing, duplicates preserved (a repeated
  misspelling is listed each time it appears).

No `check` subcommand keyword was added: the page's
examples use the bare filter-file form, and adding a second
spelling of the same command would be speculative surface.

## Success criteria (verifiable)

- Every inserted word is reported present (no false
  negatives) — unit-tested, not just asserted by design.
- Measured false-positive rate on held-out words is
  reported by a test and bounded (see TEST_PLAN.md).
- A saved filter round-trips byte-exactly through the
  documented header, and corrupt headers are rejected.
- CLI build + check end-to-end in a temp directory, using
  the page's example words, reproduces the page's output
  format for the words absent from the test dictionary.
