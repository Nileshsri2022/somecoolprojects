# Bitcask — SPEC

Source: https://codingchallenges.fyi/challenges/challenge-bitcask/
(slug `challenge-bitcask`, fetched 2026-10-25; first guess, no 404.)

Bitcask is a log-structured hash table: values live in append-only
log files on disk, keys plus metadata live in an in-memory hash
table ("keydir"). A read is one keydir lookup plus one seek/read.

## Challenge steps implemented

- Step 0: environment / CLI tool (Python 3 stdlib only).
- Step 1: CLI `set`/`get` against a database directory. The page's
  placeholder `Key:Value` whole-file rewrite is superseded by Step 2
  onwards, so the final implementation does not keep that format;
  the CLI surface (`-db DIR set/get/del`) is kept.
- Step 2: append-only log files. Each record is

  ```
  CRC-32 (4 bytes, little-endian)
  timestamp (4 bytes, little-endian, seconds since epoch)
  key size (4 bytes, little-endian)
  value size (4 bytes, little-endian)
  key bytes
  value bytes
  ```

  CRC-32 (`zlib.crc32`) is computed over everything after the CRC
  field (timestamp, sizes, key, value). Records are appended at the
  end of the active file. When the active file would exceed
  `max_file_size` after a write, it is closed and a new active file
  is created (rotation happens after the overshooting write, so a
  single record is never split across files).
- Step 3: keydir entry per key: `(file_id, value_offset, value_size,
  timestamp)`, where `value_offset` is the absolute offset of the
  value bytes inside its log file. Only metadata, never the value,
  is kept in memory.
- Step 4: `get` seeks to `value_offset` in the recorded file and
  reads `value_size` bytes. Updating a key appends a new record and
  replaces its keydir entry; old records become garbage until merge.
- Step 5: deletion appends a tombstone record and removes the key
  from the keydir, so `get` returns nothing (`(nil)` on the CLI).
  Tombstone on disk: a record with `value_size = 0xFFFFFFFF`
  (the maximum uint32) and no value bytes. This is the on-disk
  marker that distinguishes "deleted" from "stored empty value"
  (a real empty value has `value_size = 0` and is retrievable).
- Step 6: merge (compaction). A merge iterates over all non-active
  (immutable) files and rewrites only the live version of each key
  into new files, writes a hint file beside each new file, then
  deletes the old files. Hint record format (no CRC; hints are
  derived data, see DESIGN.md):

  ```
  timestamp (4 bytes, little-endian)
  key size (4 bytes, little-endian)
  value size (4 bytes, little-endian)
  value position (8 bytes, little-endian, absolute offset in data file)
  key bytes
  ```

  On startup, records are replayed in file-id order; a bad CRC or a
  truncated tail stops scanning that file and the tail is discarded
  (truncated if it is the active file), which is the crash-recovery
  behaviour. Hint files, when present and well-formed, are used to
  rebuild the keydir for immutable files faster; a malformed hint
  falls back to a full scan of the data file.

## Files in a database directory

- `cask.<id>` — log files, ids starting at 0, increasing. The
  highest id is the active (appendable) file; all others are
  immutable. This follows the page's Step 1 suggestion (`cask.0`).
  Merge ends with a rotation so this invariant holds after every
  merge (see DESIGN.md).
- `cask.<id>.hint` — hint file for a merged file (only merge
  produces these).
- `ACTIVE` — small file naming the active file id, so recovery
  does not have to assume the active file is the highest id (it
  is, except after a merge interrupted before its final rotation;
  recovery rotates in that case).
- `bitcask.lock` — lock file held with an exclusive non-blocking
  `flock` while the database is open, enforcing the page's
  "only one process at a time" rule. The lock is released by the
  OS if the process dies, so a crash does not leave a stale lock.

## CLI

```
python3 bitcask.py -db ./database set Key Value
python3 bitcask.py -db ./database get Key      # prints value or (nil)
python3 bitcask.py -db ./database del Key
python3 bitcask.py -db ./database merge
python3 bitcask.py -db ./database list         # extra: sorted keys, one per line
```

`list` is an addition beyond the page (useful for inspection and
testing); it is not required by any step. Keys/values on the CLI
are UTF-8 text. `get` of a missing/deleted key prints `(nil)` and
exits 0, matching the page's Step 5 example.

## Library API

```python
from bitcask import Bitcask
db = Bitcask(directory, max_file_size=1024)  # bytes; default 1 MiB
db.put("key", "value")      # str or bytes in, str or bytes out via get
db.get("key")               # bytes, or None if missing/deleted
db.delete("key")            # no-op for a missing key
db.merge()
db.keys()                   # sorted list of live keys (bytes)
db.close()                  # also usable as a context manager
```

`get` returns `bytes` (or `None`); callers decode as needed.
`close()` is idempotent. Using a database after `close()` raises
`ValueError`.
