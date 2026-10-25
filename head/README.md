# head — Build Your Own head

Coding Challenges #34, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Prints the first N lines (default 10) or N bytes of files
or standard input. Python 3 standard library only, single
file `head.py`, bytes throughout so binary input passes
through verbatim.

## Usage

```sh
python3 head.py test.txt
python3 head.py -n1 test.txt
python3 head.py -n 10 test.txt
python3 head.py -c 31 test.txt
python3 head.py -n 10 one.txt two.txt
python3 head.py -q -n 5 one.txt two.txt
python3 head.py -v -n 5 one.txt
cat test.txt | python3 head.py
python3 head.py - < test.txt
python3 head.py -n -2 test.txt   # all but the last 2 lines
python3 head.py -c -3 test.txt   # all but the last 3 bytes
```

- No operands, or `-` as an operand, reads standard input.
- Multiple files get `==> name <==` headers with a blank
  line between files; `-v` forces headers, `-q` suppresses
  them. `-` is shown as `standard input` in a header.
- The last of `-n`/`-c` on the command line wins.
- Errors (missing file, directory, invalid count, unknown
  option) go to stderr with exit status 1; file errors do
  not stop later files.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests compare stdout, stderr and exit status byte-for-byte
against system `head` on the same fixtures, plus the error
cases above and the challenge page's own examples.

## Deliberate divergences

- No byte-count suffix multipliers (`-c 1K` is an invalid
  number) and no `-z`/`--zero-terminated` option; the
  challenge page does not require either.
- `--version` is an unknown option; `--help` prints a
  short usage message of our own, not GNU's.
- Error prefix is `head:`, matching the tool name.
