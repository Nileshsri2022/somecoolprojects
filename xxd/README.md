# xxd — Build Your Own Xxd

Coding Challenges #43, worked in `somecoolprojects/`.
Docs first, then code — see `docs/` (SPEC, DESIGN, TEST_PLAN).

A hex-dump tool and its reverse: dump a file as offset + hex +
ASCII, or convert a hex dump back to binary. Python 3 standard
library only, single file.

## Usage

```sh
python3 xxd.py files.tar | head -n 10
python3 xxd.py -e files.tar | head -n 2
python3 xxd.py -e -g 8 files.tar | head -n 2
python3 xxd.py -l 16 -c 4 files.tar
python3 xxd.py -s 512 -l 16 files.tar
python3 xxd.py files.tar > files.hex
python3 xxd.py -r files.hex > files.restored
```

Output format (16 bytes per line by default):

```
00000000: 6669 6c65 312e 7478 7400 0000 0000 0000  file1.txt.......
```

Options: `-e` little-endian groups (default group 4 in `-e` mode,
else 2), `-g` octets per group (power of two, 1–256), `-c` bytes
per line (1–256, default 16), `-l` byte limit, `-s` seek offset
(decimal or `0x` hex; negative counts back from EOF), `-r`
reverse mode. No input file means stdin; a second positional
argument is an output file. In reverse mode `-r -e` un-reverses
groups so `-e` dumps round-trip, and `-s` positions the output.

Reverse input accepts the tool's own dump format (offset + hex +
ASCII column) and plain hex with no offsets; the ASCII column is
ignored even if it looks like hex. Invalid hex, bad `-g`/`-c`,
and missing files fail with a stderr message and a non-zero exit.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

40 tests, all passing: the page's Step 1–4 example lines verbatim,
grouping/columns/length/seek, dump→revert round-trips (text, all
256 byte values, empty input, `-e` mode), reverse-mode parsing
edge cases, and CLI exit codes. Tests use temp files only.

## Divergences / caveats

- **System `xxd` comparison was not possible**: `xxd` is not
  installed in this environment, so no byte-for-byte diff against
  it was run. The page's own example lines are the oracle instead
  (encoded verbatim in the tests). Where `xxd` exists, compare
  with `xxd <file> | diff - <(python3 xxd.py <file>)`.
- **`-e` spacing vs the page's Step 2 examples**: the page's `-e`
  lines appear to show three spaces before the ASCII column, while
  Steps 1/3/4 show two. This implementation uses a uniform
  two-space separator (full and partial lines alike, with the hex
  field padded so ASCII aligns). If a real-`xxd` diff shows three
  spaces in `-e` mode, that is the first thing to fix.
- **`-g` validity rule**: the page says only "handle invalid
  values"; this implementation requires a power of two in 1–256.
- **Not implemented** (not on the page): `-p`, `-u`, `-b`, `-o`,
  `-v`, autoskip `*` lines.
