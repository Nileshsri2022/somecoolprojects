# bitcask — Build Your Own Bitcask

Coding Challenges entry 70, worked in `somecoolprojects/`.
Docs first, then code — see `docs/` (SPEC, DESIGN, TEST_PLAN).

A log-structured hash table: values live in append-only log
files (`cask.<id>`) in a database directory, keys plus metadata
(file id, value offset, value size, timestamp) live in an
in-memory keydir, so a read is one lookup plus one seek.
Records carry a CRC-32; deletion writes a tombstone record
(`value_size = 0xFFFFFFFF`); `merge` compacts immutable files,
keeping only live records, and writes `.hint` files beside the
new files. On open, logs are replayed (hint fast-path for
immutable files, full scan otherwise); a torn/corrupt tail in
the active file is truncated so later appends stay clean.

Python 3 standard library only. Single main file: `bitcask.py`.

## Usage

```sh
python3 bitcask.py -db ./database set Key Value
python3 bitcask.py -db ./database get Key      # prints value or (nil)
python3 bitcask.py -db ./database del Key
python3 bitcask.py -db ./database merge
python3 bitcask.py -db ./database list         # extra, not in the challenge
```

Library use:

```python
from bitcask import Bitcask
with Bitcask("./database", max_file_size=1024) as db:
    db.put("Key", "Value")
    db.get("Key")   # b"Value"
    db.delete("Key")
    db.merge()
```

`max_file_size` defaults to 1 MiB (Riak uses 2 GB); the CLI
accepts `--max-file-size N` after `-db DIR`. Only one process
may open a database at a time (exclusive `flock` on
`bitcask.lock`, released by the OS on crash).

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

17 tests, all in temporary directories: put/get/overwrite,
empty vs deleted values, binary keys/values, rotation across
files, reopen-after-close recovery, torn-tail and CRC-corruption
recovery, tombstone survival, merge (live kept, dead dropped,
hint replay, post-merge overwrite), lock, use-after-close, and
the CLI commands.
