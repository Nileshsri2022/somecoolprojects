# tar — Build Your Own Tar Tool

Coding Challenges entry 42, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Creates, lists, and extracts UStar tarballs with a
hand-written 512-byte header implementation. Python 3
standard library only, single file `tar_tool.py`.

## Usage

```sh
python3 tar_tool.py -tf files.tar        # list
cat files.tar | python3 tar_tool.py -t   # list from stdin
python3 tar_tool.py -tvf files.tar       # list, verbose
python3 tar_tool.py -xf files.tar        # extract
python3 tar_tool.py -cf files.tar file1.txt file2.txt file3.txt
```

- `-c` / `-t` / `-x` may be clustered with `-f` and `-v`
  (`-tf`, `-cf`, `-xf`, `-tvf`) or given separately.
  Without `-f`, create writes to stdout and list/extract
  read from stdin.
- Files, directories (recursively, sorted), empty
  directories, and symlinks (stored, not followed) are
  supported. Modes and mtimes are preserved on extract.
- Archives end with two 512-byte zero blocks.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use temp directories only and verify round-trips
against system `tar` where it is installed; `tarfile`
is used only as a test oracle, never by `tar_tool.py`.

## Deliberate divergences

- The page suggests `diff`ing a created archive against
  system tar's byte-for-byte. That is not claimed:
  system tar pads to a 10240-byte blocking factor and
  orders directory entries differently, while this tool
  writes exactly two zero blocks and walks directories
  in sorted order. Both archives are valid UStar and
  interchangeable (system tar lists/extracts ours, and
  vice versa) — that is what the tests check.
- Unsafe extraction paths (absolute or `..`-escaping
  entries, absolute symlink targets) are refused with an
  error, where GNU tar would strip/adjust them.
- No gzip (`.tar.gz`): the page lists it only under
  "Going Further". No pax headers on write, hard links,
  devices, or fifos.
- `-v` list format is this tool's own
  (`mode owner/group size date name`); the page
  specifies no verbose format.
