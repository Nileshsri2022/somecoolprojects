# cat — Build Your Own cat Tool

Coding Challenges #15, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Concatenates files (and standard input) to standard output,
with line numbering. Python 3 standard library only, single
file `cat.py`, bytes throughout so binary input passes
through verbatim.

## Usage

```sh
python3 cat.py one.txt
python3 cat.py one.txt two.txt
python3 cat.py - < one.txt
cat one.txt | python3 cat.py
python3 cat.py -n one.txt
python3 cat.py -b one.txt
python3 cat.py -n one.txt two.txt
python3 cat.py -- -n          # file literally named -n
```

- No operands, or `-` as an operand, reads standard input.
- `-n`: number every line. `-b`: number only non-blank
  lines; blank lines are printed unchanged. If both are
  given, `-b` wins (as with system cat).
- Line numbering continues across concatenated files.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests compare output byte-for-byte against system `cat`
on the same fixtures, plus error cases (missing file,
directory, unknown option).

## Deliberate divergences

- Number format follows system cat (`%6d` + tab, e.g.
  `     1\ttext`), not the challenge page's simplified
  display (`1  text`). The page's examples are illustrative
  (its `-b` example also omits the interleaved blank lines
  that `sed G` actually produces); matching real cat is
  what the byte-for-byte tests check.
- Error messages are prefixed `ccat:` (repo convention,
  as with `ccut:`/`ssort:`), not system cat's `cat:`.
  Exit status and continue-on-error behaviour match.
- Only `-n` and `-b` are implemented. The page asks for
  nothing else, so this is not a full GNU cat clone
  (no `-E`, `-T`, `-s`, `-v`).
