# tr Tool — DESIGN

## Implementation

Single file, Python 3 standard library only: `tr_tool.py`.
No helpers are needed; the whole tool is one module so it can
be run as `python3 tr_tool.py ...` and imported by the tests
(`parse_set`, `build_translation`, `process` are importable).

## Pipeline

```
argv ──► parse_args ──► parse_set(string1), parse_set(string2)
        (flags, operands,            (ordered byte lists;
         mode validation)             repeat in string2 resolved
                                      against len(string1))
              │
              ▼
   build mode structures:
     delete_set  : set[int] | None
     trans_table : bytes translation table (256 entries) | None
     squeeze_set : set[int] | None
              │
              ▼
   stream stdin buffer in 64 KiB chunks:
     chunk ──► translate/delete via bytes.translate(table, delete)
           ──► squeeze scan (only if squeeze_set is set),
                carrying prev_output_byte across chunks
           ──► write chunk to stdout buffer, flush
```

Order of operations inside one chunk is exactly the man-page
order: delete, then translate, then squeeze. `bytes.translate`
does delete + translate in a single C-level pass, which is both
fast and the reason Step 6 (scale) is cheap: the per-byte Python
loop runs only for squeezing, and only when `-s` is in effect.

## Set parsing (`parse_set`)

The parser walks the raw bytes of the specification with an
index, producing an ordered list of ints (a list, not a set, so
that translation pairing and class ordering are preserved).

State machine, in priority order at each position:

1. Backslash: consume the escape (named escape, 1–3 octal
   digits, or the next byte literally). The resulting byte is a
   single "atom".
2. `[:name:]`: if the text from `[` matches `[:` + name + `:]`
   with a plausible name (letters only), expand to the class
   byte list (ascending order); if the name is unknown, raise
   `TrError`. If the text does not match that shape at all
   (e.g. `[abc`), `[` is a literal atom. This mirrors system
   `tr`: `[abc` is literal, `[:foo:]` is an error.
3. `[=c=]`: if the text matches `[=` + one byte + `=]`, that
   byte is an atom. A well-formed-looking `[=...=]` with a
   length other than one byte raises `TrError`; otherwise `[`
   is literal.
4. `[c*n]` / `[c*]`: `c` is a single byte (possibly escaped);
   `n` is decimal, or octal if it starts with `0` and has more
   than one digit. `n` omitted or 0 is a fill sentinel meaning
   "fill to len(string1)", resolved later by `resolve_fills`
   once string1 is known. An explicit count is valid in either
   set; a fill in string1 is rejected by the caller
   (`build_config` / `build_translation`) before any input is
   read. A non-repeat bracket expression falls through to the
   literal rule.
5. Any other byte: a single atom.

Range handling is a second pass over the atom stream, not part
of the scan above, because a class expansion must not take part
in a range: after scanning, the atom list is a list of items,
each either a single byte or a class expansion (a list of
bytes). Walking that list, a single byte, followed by a literal
`-` atom, followed by a single byte, collapses to the inclusive
range — unless the `-` is first or last (then it stays literal)
or either endpoint is a class expansion (then the `-` stays
literal, matching system `tr`, which does not allow ranges
whose endpoints are classes). A reversed range raises
`TrError`. Note the scan must therefore distinguish a `-` that
was escaped (`\-` → literal hyphen atom, never a range
operator) from a bare `-`; the implementation tags atoms as
`(value, is_range_operator)` for bare `-` only... in practice
this is done by keeping bare `-` as a distinct sentinel object
in the atom list and converting everything else to ints before
the range pass. A `-` immediately following a class expansion
is literal because the range pass only fires when both
neighbours are single-byte atoms.

Duplicate bytes in string1: the translation table is built by
iterating string1 in order and overwriting, so the last
pairing wins (verified against system `tr`).

## Translation table (`build_translation`)

Given expanded string1 (`s1`) and expanded string2 (`s2`,
repeats already resolved):

- Complement (`-c`): `s1 = [b for b in range(256) if b not in set(s1)]`.
- If `-t`: `s1 = s1[:len(s2)]`; the table maps those bytes only.
- Else if `len(s2) < len(s1)`: pad `s2` with `s2[-1]` to
  `len(s1)`. If `s2` is empty and not truncating: `TrError`.
- Table starts as identity (`bytes(range(256))`); for each
  `(a, b)` pair, `table[a] = b` unless `a` already mapped.

The squeeze set for translate+`-s` is `set(s2_as_written)` —
the expanded string2 *before* padding. This was verified
against system `tr`: `printf 'AAABBB' | tr -s 'ab' 'A'` gives
`ABBB` (only `A` squeezes, not the padded `B→A` mapping),
while `tr -s 'a-z' 'A'` on `aaabbb` gives `A` (both map to
`A`, and `A` is the squeeze set). Padding bytes do not join
the squeeze set.

## Delete and squeeze sets

- Delete set: `set(s1)`; with `-c`, its complement. Passed as
  the `delete` argument to `bytes.translate`, or applied
  alone when there is no translation table.
- Squeeze set:
  - squeeze-only: `set(s1)` (complemented with `-c`);
  - `-ds`: `set(s2)` (not complemented, even with `-c` — the
    complement applies to the delete set only);
  - translate+`-s`: `set(s2_as_written)` as above.
- Squeeze scan: iterate the chunk; keep `prev` (last byte
  actually written, or `None` at start). A byte is dropped iff
  it is in the squeeze set and equals `prev`; otherwise it is
  emitted and becomes `prev`. `prev` persists across chunks.

## Argument parsing (`parse_args`)

Hand-rolled, deliberately small (no `argparse`: `tr`'s operand
rules — e.g. `-d` changing the valid operand count — do not
fit `argparse` cleanly, and error messages should match `tr`'s
shape, not `argparse`'s).

- Scan leading arguments: `--` ends option parsing; an
  argument starting with `-` (and longer than one byte) while
  no operand has been seen is an option cluster: each byte
  must be one of `c C d s t u` (long options handled before
  clustering: `--delete`, `--squeeze-repeats`,
  `--complement`, `--truncate-set1`, `--help`). Unknown
  option byte → `TrError`. A lone `-` is an operand, not an
  option (so `tr -d -` deletes `-`).
- Once the first operand is seen, everything else is an
  operand, even if it starts with `-`.
- Mode validation (see SPEC table) happens after parsing,
  before any input is read, so errors never produce partial
  output.

## Streaming and errors

- `sys.stdin.buffer.read(65536)` / `sys.stdout.buffer.write`
  in a loop; each chunk flushed, so `-u` behaviour holds
  trivially and a downstream `head` sees output promptly.
- `TrError` → message `tr_tool.py: <msg>` on stderr, exit 1.
- `BrokenPipeError` on write: close stdout quietly, exit 0
  (system `tr` dies on SIGPIPE; a quiet exit is the closest
  Python equivalent without a traceback).
- `KeyboardInterrupt`: exit 130, no traceback.

## Why bytes, not str

`tr` is a byte filter: the page's examples are text, but
nothing in the spec is text-only, and a `str` implementation
would corrupt NUL/high bytes and mis-handle non-UTF-8 input.
`os.fsencode` recovers the raw bytes of set arguments, so a
set can itself contain high bytes passed by the shell.

## Alternatives considered

- `argparse`: rejected (see above); its usage errors and
  exit code 2 would diverge from `tr`'s exit code 1.
- Translating with a per-byte Python loop: rejected for
  speed; `bytes.translate` is a single C pass, and the
  squeeze loop only runs when squeezing.
- Decoding input as UTF-8 and translating code points:
  rejected; byte semantics match both the BSD man page's
  single-byte behaviour and GNU `tr` in the C locale.
