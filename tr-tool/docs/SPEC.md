# tr Tool — SPEC

## Challenge

Build your own version of the Unix command line tool `tr`
(translate, delete, squeeze characters).

- Resolved challenge page (read before writing anything; found via
  the `unix` tag page, not guessed):
  <https://codingchallenges.fyi/challenges/challenge-tr>
- Original newsletter version: Coding Challenge #43 — tr
  (<https://codingchallenges.substack.com/p/coding-challenge-43-tr>).
  The fyi page is the spec followed here; the two agree on Steps 0–6.
- Tags on codingchallenges.fyi: intermediate, cli (also listed
  under the `unix` tag).
- The page's own summary: "The TL/DR version is `tr` swaps,
  squeezes or deletes characters." Its functional requirements are
  the `tr` man page it quotes (BSD synopsis):

  ```
  tr [-Ccsu] string1 string2
  tr [-Ccu] -d string1
  tr [-Ccu] -s string1
  tr [-Ccu] -ds string1 string2
  ```

## Steps from the page, and how each is met

### Step Zero — setup / test input

The page asks for `curl https://www.gutenberg.org/cache/epub/132/pg132.txt
-o test.txt` (The Art of War) as test input. No network fetch is
needed to build or test this tool: the tests use small inline inputs
plus the page's own examples, and byte-compare against system `tr`
(GNU coreutils 9.4, present in this environment) as the oracle.
Step 6's scale check is done with a generated large input instead
of a 3,000× copy of the Gutenberg text (same property: streaming,
bounded memory, correct output on a large stream).

### Step 1 — single-character translation

Read standard input, write standard output with substitutions
applied, terminate on EOF (Ctrl-D at a terminal). Example from
the page:

```
% cctr c C
coding challenges
Coding Challenges
```

Implemented: `python3 tr_tool.py c C` (program name differs; see
Divergences). Input is read as bytes, so this works for a whole
stream, not just one line at a time.

### Step 2 — ranges

Ranges are start–end separated by a hyphen, e.g. `A-Z`, `a-z`.
Example from the page:

```
% head -n3 test.txt | cctr A-Z a-z
the project gutenberg ebook of the art of war
```

Implemented, including ranges built from escaped endpoints
(e.g. `\0-\377` is not special-cased; any single-byte endpoints
work) and a reversed range (`z-a`) rejected with an error,
matching system `tr`.

### Step 3 — character classes `[:class:]`

The page lists, from the man page: alnum, alpha, blank, cntrl,
digit, lower, print, punct, rune, space, special, upper. Example:

```
% head -n3 test.txt | cctr "[:upper:]" "[:lower:]"
```

Implemented for the ASCII classes: alnum, alpha, blank, cntrl,
digit, graph, lower, print, punct, space, upper, xdigit.
`graph` and `xdigit` are included even though the page's excerpt
omits them, because they are standard classes and system `tr`
supports them; supporting extra standard classes is not a
divergence from any page example.

NOT implemented (see Divergences): `rune`, `special`,
`ideogram`, `phonogram`. These are locale-dependent BSD classes
with no byte-level definition; system `tr` (GNU, the oracle used
here) rejects them too (`invalid character class 'rune'`).

### Step 4 — delete with `-d`

```
tr [-Ccu] -d string1
```

Examples from the page:

```
% head -n3 test.txt | cctr -d War
The Poject Gutenbeg eBook of The At of
% head -n3 test.txt | cctr -d "[:upper:]"
he roject utenberg eook of he rt of ar
```

Implemented, including `-d` with classes and ranges, and `-c`
(complement) with `-d` — delete everything *except* the set.

### Step 5 — squeeze with `-s`, and `-ds`

```
tr [-Ccu] -s string1
tr [-Ccu] -ds string1 string2
```

Squeeze collapses each run of a listed character into a single
instance, after deletion and translation are complete. Examples
from the page:

```
% cctr -s AB
AAABBBCCC
ABCCC
% head -n10 test.txt | cctr -ds "[:alnum:]" "[:space:]"
```

Implemented: `-s` alone squeezes the set in string1; `-s` with
translation squeezes the characters of string2 (as written, not
the padded translation — verified against system `tr`, see
DESIGN.md); `-ds` deletes string1 then squeezes string2;
`-cs` / `-cds` complement the relevant set as system `tr` does
(complement applies to string1 in `-ds` mode; the squeeze set
itself is not complemented unless `-s` is used without `-d`).

### Step 6 — scale

The page's check pipes a large input (3,000 copies of the test
file) through `tr "[:upper:]" "[:lower:]"`. Implemented by
streaming: input is processed in 64 KiB chunks with bounded
memory, and the squeeze state (previous output byte) is carried
across chunk boundaries. The test suite includes a large-input
case (several megabytes) byte-compared against system `tr`.

### Going Further

The page invites implementing "the remaining functionality of
`tr`". Implemented beyond Steps 0–6:

- `-c` / `-C` complement (BSD `-C` and GNU `-c` are synonyms here).
- `-t` / `--truncate-set1`: truncate string1 to the length of
  string2 instead of padding string2 with its last character.
- Escapes in sets: `\a \b \f \n \r \t \v \\`, `\ooo` (1–3 octal
  digits), and backslash followed by any other character meaning
  that character (including `\-` for a literal hyphen).
- Repeat in string2: `[c*n]` (n decimal, or octal when it has a
  leading zero, per the BSD man page) and `[c*]` / `[c*0]`
  meaning "repeat enough to fill string1".
- Equivalence `[=c=]`, meaning just the single character `c`
  (the byte-mode equivalence class of an ASCII character is
  itself). Valid in string1 and in delete/squeeze sets, but
  NOT in string2 when translating (system `tr`'s rule:
  `[=c=] expressions may not appear in string2 when
  translating`).
- Long options `--delete`, `--squeeze-repeats`, `--complement`,
  `--truncate-set1`, `--help`, and `--` to end option parsing.
- `-u` accepted as a no-op: output is already unbuffered in
  effect (each processed chunk is written immediately; a flush
  follows every chunk).

## Behaviour specification

### Invocation

```
python3 tr_tool.py [-cCds tu] [string1 [string2]]
python3 tr_tool.py --delete string1
python3 tr_tool.py --squeeze-repeats string1
python3 tr_tool.py --delete --squeeze-repeats string1 string2
python3 tr_tool.py -- string1 string2        # set starting with '-'
```

Modes, by flags and operand count:

| Flags | Operands | Meaning |
| ----- | -------- | ------- |
| (none) | 2 | Translate string1 → string2. |
| `-d` | 1 | Delete characters in string1. |
| `-s` | 1 | Squeeze characters in string1. |
| `-s` | 2 | Translate, then squeeze characters of string2. |
| `-d -s` | 2 | Delete string1, then squeeze string2. No translation. |
| `-d` | 2 | Error: `-d` takes exactly one operand unless `-s` is also given. |
| `-s` with `-d` | 1 | Error: `-ds` needs two operands. |
| any | 0 | Error: missing operand. |
| (none) | 1 | Error: translating needs two operands. |

Operand-count and set errors print a message to stderr and exit
with status 1, matching system `tr`'s exit status for these
errors. Unknown options also exit 1.

### Sets

Sets are sequences of bytes (0–255). A set specification is
parsed left to right into an ordered list of bytes (duplicates
kept at parse time; translation uses the first mapping for a
duplicated byte in string1, and the delete/squeeze sets are
treated as membership sets, so duplicates there are harmless).

Elements:

- A literal byte stands for itself, except `-` (range operator,
  see below), `\` (escape introducer), `[` when it starts a
  recognised `[::]`, `[==]` or `[*]` construct.
- Range `lo-hi`: every byte from `lo` to `hi` inclusive, in
  ascending order. `lo` and `hi` are single bytes (possibly
  escaped). A reversed range is an error. A `-` at the start or
  end of a set, or immediately after a class/repeat construct,
  is literal.
- Escape `\a` (7), `\b` (8), `\f` (12), `\n` (10), `\r` (13),
  `\t` (9), `\v` (11), `\\` (92), `\ooo` (1–3 octal digits,
  value modulo 256 — values above 255 from a 3-digit octal such
  as `\400` wrap, matching the "octal" reading; in practice
  `\377` is the largest useful value), and `\x` for any other
  byte `x` meaning `x` itself. A trailing lone backslash is a
  literal backslash (system `tr` prints a portability warning
  for this spelling; this tool treats it the same way silently).
- Class `[:name:]` expands, in ascending byte order, to:
  - alnum: `0-9A-Za-z`
  - alpha: `A-Za-z`
  - blank: tab, space
  - cntrl: 0–31, 127
  - digit: `0-9`
  - graph: 33–126
  - lower: `a-z`
  - print: 32–126
  - punct: graphic characters that are not alphanumeric
    (33–47, 58–64, 91–96, 123–126)
  - space: tab, newline, vertical tab, form feed, carriage
    return, space (9–13, 32)
  - upper: `A-Z`
  - xdigit: `0-9A-Fa-f`
  - Any other class name is an error (`invalid character class`).
  - A malformed `[:...` without a closing `:]` is treated as
    the literal characters `[`, `:`, … (matching system `tr`'s
    treatment of a non-class bracket expression as literal text,
    except that a well-formed-looking but unknown class is an
    error, not literal text).
- Repeat `[c*n]`: the byte `c` repeated `n` times. An explicit
  count is valid in either set. `n` omitted or 0 means "repeat
  enough to make string2 as long as string1" (resolved at
  translation-table build time, after string1 is known) and is
  valid in string2 only — a fill repeat in string1 is an error
  (`the [c*] repeat construct may not appear in string1`,
  system `tr`'s message). `n` with a leading zero is read as
  octal, otherwise decimal.
- Equivalence `[=c=]`: the single byte `c`. Malformed
  `[=...]` is literal text only if it does not parse; a
  well-formed `[=xy=]` (more than one byte) is an error; and
  any `[=c=]` in string2 when translating is an error (above).

### Translation

- Pair the i-th byte of string1 with the i-th byte of string2.
- If string2 is shorter than string1, pad string2 with its last
  byte — unless `-t` is given, in which case string1 is
  truncated to string2's length and the remaining string1 bytes
  pass through unchanged.
- If string2 is empty while translating (and `-t` is not in
  play), that is an error: `when not truncating set1, string2
  must be non-empty` (system `tr`'s message).
- An empty string1 is allowed and is a no-op (delete nothing,
  translate nothing, squeeze nothing), matching system `tr`.
  The empty-string2 error below applies only when string1 is
  non-empty.
- With `-c`, string1 is first replaced by its complement (all
  bytes 0–255 not in string1, in ascending order), then paired
  with string2 as above.
- A byte not in string1 passes through unchanged.
- If string1 contains a byte twice, the last pairing wins
  (verified against system `tr`: `tr 'aab' 'XYZ'` maps `a` to
  `Y`, not `X`).

### Delete

- Every input byte in the delete set is dropped. With `-c`,
  the delete set is complemented first (everything except the
  set is dropped).
- Delete happens before translation and squeezing.

### Squeeze

- After delete/translate, any run of the same byte, where that
  byte is in the squeeze set, collapses to one instance.
- The squeeze set is: string2 as written for translate+`squeeze`
  and for `-ds`; string1 for squeeze-only; the complement of
  string1 for `-cs` (squeeze-only with complement); for `-cds`,
  the delete set is complemented but the squeeze set (string2)
  is not — matching system `tr`.
- Squeeze state is carried across input chunks, so a run split
  by a chunk boundary is still squeezed to one.

### Bytes, not text

All processing is on bytes. No decoding is attempted, so
arbitrary binary input (including NUL and high bytes) passes
through correctly except as translated/deleted/squeezed. Set
specifications themselves are taken from the command line as
bytes via `os.fsencode`, so a non-ASCII set argument is treated
as its raw bytes, not as decoded text.

### Errors

- Missing/extra operands, empty string2 when translating a
  non-empty string1, reversed range, unknown character class,
  fill repeat in string1, malformed repeat/equivalence,
  unknown option: message to stderr, exit status 1, no partial
  output guarantee (errors are detected before any input is
  read, so in practice nothing is written before an error).
- Broken pipe on output (e.g. piping to `head`): the program
  exits quietly instead of printing a traceback.

## Divergences from the page / from system tr

1. Program name: the page calls the example binary `cctr`; this
   build is `tr_tool.py`, run with `python3 tr_tool.py`. The
   behaviour, not the name, is what is tested.
2. BSD classes `rune`, `special`, `ideogram`, `phonogram` are
   NOT supported (error, as with GNU `tr`). They are
   locale-dependent (valid multibyte characters, ideographs,
   phonograms) and have no definition in a byte-oriented tool.
   All other classes in the page's list are supported.
3. BSD `-u` (unbuffered) is accepted but is a no-op: output is
   already written chunk-by-chunk. There is no observable
   difference for a pipe consumer.
4. The page's Step 0 Gutenberg download is not part of the
   build or the tests (see Step Zero above); large-input
   behaviour is tested with generated data instead.
5. GNU `tr` prints a portability warning for a trailing
   backslash in a set; this tool treats the backslash as
   literal silently (same mapping, no warning). Otherwise the
   error paths above were checked against GNU `tr` and match
   it on exit status 1; only the message wording differs in
   some operand-count cases.
6. No locale support: classes are fixed ASCII definitions
   regardless of `LANG`/`LC_*`, matching GNU `tr` in the C
   locale, which is the environment the tests run in.

## Scope limits — explicitly NOT built

- No file operands: input is standard input only, output is
  standard output only (as `tr` itself works; the page never
  asks for file operands).
- No multibyte/UTF-8 character handling: bytes only.
- No locale-dependent collation: ranges are by byte value.
- No BSD classes `rune`/`special`/`ideogram`/`phonogram`
  (see above).
- No `--help` output beyond a short usage summary (no man page).
