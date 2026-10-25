# tr Tool — Build Your Own tr

Coding Challenges, worked in `somecoolprojects/`.
Docs first, then code — see `docs/` (`SPEC.md`, `DESIGN.md`,
`TEST_PLAN.md`).

A byte-oriented clone of the Unix `tr` command: translate,
delete, and squeeze characters, reading standard input and
writing standard output. Python 3 standard library only,
single file `tr_tool.py`.

Challenge page (read first, via the `unix` tag page):
<https://codingchallenges.fyi/challenges/challenge-tr>

## Usage

```sh
python3 tr_tool.py c C                  # Step 1: c -> C
echo "coding challenges" | python3 tr_tool.py c C
# Coding Challenges

head -n3 test.txt | python3 tr_tool.py A-Z a-z
head -n3 test.txt | python3 tr_tool.py "[:upper:]" "[:lower:]"
head -n3 test.txt | python3 tr_tool.py -d War
head -n3 test.txt | python3 tr_tool.py -d "[:upper:]"
printf 'AAABBBCCC' | python3 tr_tool.py -s AB   # ABCCC
head -n10 test.txt | python3 tr_tool.py -ds "[:alnum:]" "[:space:]"

python3 tr_tool.py -c a-z X             # complement: non-lowercase -> X
python3 tr_tool.py -d -c a-z            # delete everything except a-z
python3 tr_tool.py -t abc XYZW          # truncate set1 to set2 length
python3 tr_tool.py -- -a b              # set starting with '-'
```

Flags: `-c` / `-C` complement, `-d` delete, `-s` squeeze,
`-t` truncate set1, `-u` accepted (no-op: output is already
written chunk-by-chunk). Long options: `--delete`,
`--squeeze-repeats`, `--complement`, `--truncate-set1`,
`--help`. Combine flags, e.g. `-ds`, `-cds`.

## Sets

- Literals, ranges (`A-Z`, `a-z`, `0-9`), escapes
  (`\n \t \r \a \b \f \v \\`, octal `\ooo`, `\-` for a
  literal hyphen).
- Classes: `[:alnum:] [:alpha:] [:blank:] [:cntrl:]
  [:digit:] [:graph:] [:lower:] [:print:] [:punct:]
  [:space:] [:upper:] [:xdigit:]`.
- Repeat: `[c*n]` (decimal, or octal with a leading zero) in
  either set; `[c*]` / `[c*0]` = fill to string1's length, in
  string2 only (an error in string1, as with system `tr`).
- Equivalence: `[=c=]` = the single character `c` (not in
  string2 when translating, as with system `tr`).

Supported / not supported, exactly:

- Supported: translate, delete, squeeze, `-ds`, complement,
  truncate, ranges, classes above, escapes, repeats,
  equivalence, byte/binary input, streaming large input.
- NOT supported: BSD locale classes `[:rune:]`,
  `[:special:]`, `[:ideogram:]`, `[:phonogram:]`
  (rejected with an error, as GNU `tr` also rejects them);
  multibyte/UTF-8 characters (bytes only); file operands
  (stdin/stdout only, as with real `tr`); locale-dependent
  collation (fixed ASCII classes).

Errors (missing/extra operands, empty string2 when translating,
reversed range, unknown class, fill repeat in string1,
unknown option) print a message to stderr and exit 1, before
any input is read, so no partial output is produced.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

The suite byte-compares against system `tr` (GNU coreutils)
where it is available, and skips those oracle cases cleanly
where it is not. See `docs/TEST_PLAN.md` for coverage.
