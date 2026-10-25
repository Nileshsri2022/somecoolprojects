# Tar — Specification

Source: https://codingchallenges.fyi/challenges/challenge-tar/
Slug used: `challenge-tar` (first guess; no 404, no correction needed).

Challenge steps implemented, in page order:

- **Step 0** — Test fixture: `file1.txt`, `file2.txt`, `file3.txt`
  archived with system tar as `files.tar`.
- **Step 1 — List** — `cat files.tar | tar_tool.py -t` prints one
  name per line; `tar_tool.py -tf files.tar` reads the file
  directly. Names are printed exactly as stored.
- **Step 2 — Extract** — `tar_tool.py -xf files.tar` recreates
  the files with their contents (size-checked, `diff`-clean).
- **Step 3 — Create** — `tar_tool.py -cf files.tar file1.txt
  file2.txt file3.txt` writes a valid UStar archive readable
  by system `tar` (list and extract) and by this tool.

## UStar 512-byte header (offsets, sizes in bytes)

| Field | Offset | Size | Encoding |
|---|---|---|---|
| name | 0 | 100 | NUL-terminated string |
| mode | 100 | 8 | octal, NUL/space terminated |
| uid | 108 | 8 | octal |
| gid | 116 | 8 | octal |
| size | 124 | 12 | octal |
| mtime | 136 | 12 | octal (seconds since epoch) |
| chksum | 148 | 8 | 6 octal digits, NUL, space |
| typeflag | 156 | 1 | `0` regular, `5` directory, `2` symlink |
| linkname | 157 | 100 | NUL-terminated string |
| magic | 257 | 6 | `ustar\0` |
| version | 263 | 2 | `00` |
| uname | 265 | 32 | NUL-terminated string |
| gname | 297 | 32 | NUL-terminated string |
| devmajor | 329 | 8 | octal (0 for regular files) |
| devminor | 337 | 8 | octal (0 for regular files) |
| prefix | 345 | 155 | NUL-terminated string (long-name prefix) |
| pad | 500 | 12 | zero bytes |

Layout rules (per page + Wikipedia UStar description linked from it):

- Each entry = one 512-byte header, then file data padded
  with zero bytes up to a multiple of 512.
- The archive ends with at least two consecutive 512-byte
  zero blocks. This tool writes exactly two (1024 bytes).
- Checksum = sum of all 512 header bytes with the chksum
  field itself treated as eight spaces (0x20).
- Numeric fields are zero-padded octal ASCII, NUL-terminated
  (mode/uid/gid: 7 digits + NUL; size/mtime: 11 digits + NUL;
  chksum: 6 digits + NUL + space).
- A name longer than 100 bytes is split at a `/` into
  prefix (<= 155 bytes) + name (<= 100 bytes); the full name
  on read is `prefix + "/" + name` when prefix is non-empty.
- On read, typeflag `0` and `\0` are both regular files.
  Entries of type `x`/`g` (pax extended headers, which this
  tool never writes) are skipped, as are GNU longname
  entries `L`/`K`, which supply the following entry's name.

## CLI

```
python3 tar_tool.py -t [-f archive]          # list (stdin if no -f)
python3 tar_tool.py -tv [-f archive]         # list, verbose
python3 tar_tool.py -x [-f archive]          # extract (stdin if no -f)
python3 tar_tool.py -c [-f archive] file...  # create (stdout if no -f)
```

Flags may be clustered (`-tf`, `-cf`, `-xf`) or separate
(`-t -f archive`). `-v` is meaningful only with `-t`.
Exit status is 0 on success, non-zero with a `tar_tool:`
error message on stderr on failure (missing file, bad
checksum, truncated archive, unsafe extraction path).
