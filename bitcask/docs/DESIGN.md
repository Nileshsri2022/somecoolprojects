# Bitcask — DESIGN

## Assumptions (stated before coding, per ponytail rules)

1. The page's record/hint diagrams are images with no accessible
   field sizes in the fetched text, so field sizes follow the
   original Bitcask paper's well-known layout: 4-byte CRC, 4-byte
   timestamp, 4-byte key size, 4-byte value size, all little-endian
   (the page itself says it believes the bytes are little-endian
   and the CRC is CRC-32). This layout is self-consistent and
   documented in SPEC.md; it is not claimed to be byte-compatible
   with Riak.
2. Single-threaded use within one process is the target; the
   cross-process guarantee is only the exclusive lock. No
   networking / RESP server (listed under "Going Further" only).
3. Keys and values are arbitrary bytes via the library; the CLI
   restricts them to UTF-8 text. No key/value size cap is imposed
   beyond the uint32 size fields; a single record larger than
   `max_file_size` still goes into one file, which is then rotated.
4. Timestamps are whole seconds (`int(time.time())`). Replay order
   (file id, then offset) is the tie-breaker, so two writes in the
   same second still resolve newest-wins.
5. `fsync` after every append: this is the "crash friendly" trade.
   It costs throughput but matches the page's recovery goal and
   keeps the recovery test honest (a record is durable once `put`
   returns).

## Data structures

- `keydir: dict[bytes, Entry]` where
  `Entry = (file_id, value_offset, value_size, timestamp)`.
  Kept in memory only; rebuilt from disk on every open.
- Active file handle: opened in append+binary mode, kept open for
  the database lifetime. Reads open the target file briefly
  (`open(..., "rb")`, seek, read) so merged/deleted files cannot
  be read through a stale handle.

## Open / recovery algorithm

1. Create the directory if needed; acquire the exclusive lock.
2. List `cask.<id>` files, sorted by numeric id. If none exist,
   start with id 0 as the active file.
3. For each file in id order:
   - If a `.hint` file exists for an immutable file, try to replay
     from the hint (fast path). If the hint is truncated, has an
     impossible size/offset, or does not consume exactly its file
     length, discard it and scan the data file instead.
   - Otherwise scan records sequentially: read the 16-byte header;
     stop at EOF (clean end) or a short header (torn tail).
     Validate `key_size`/`value_size` against the remaining file
     size (tombstone `0xFFFFFFFF` has no value bytes). Recompute
     CRC-32 over header-after-CRC + key + value; on mismatch stop
     scanning this file. A valid record updates the keydir
     (tombstone removes the key); a later record always wins
     over an earlier one for the same key.
   - The highest-id file is the active file: after scanning, if a
     bad/truncated tail was found, truncate the file at the first
     bad offset so the next append overwrites the partial record
     instead of leaving garbage in the middle of the log.
4. The active file is reopened for appending; its size seeds the
   rotation check.

Notes: hint replay trusts the hint's value positions only after
the whole hint parses cleanly; it never trusts a partial hint.
Immutable files are never truncated — a bad tail there simply
ends replay of that file (such a file should not exist except
after a crash mid-merge, and merge only deletes old files after
the new ones are fully written and fsynced).

## Rotation

After each append, if `active_size > max_file_size`, close the
active file and open a new one with the next id. Rotation is
checked after the write, never before, so no record is split.

## Merge algorithm

1. No-op when there are no immutable files (nothing to compact).
   Otherwise the merge ends with a rotation (step 6): this is what
   keeps file-id order chronological. Merged files necessarily get
   ids above the old active file, so without a final rotation a
   post-merge write to the old active file would sort below the
   merged copy on reopen and lose to it.
2. Determine the live set: for every immutable file, scan its
   records in order and keep a record only if the keydir entry
   for its key points exactly at that file and offset (this
   excludes overwritten keys, deleted keys, and keys whose live
   copy is in the active file).
3. Write kept records (in original file-id/offset order) into new
   files with ids above the current maximum, rotating by
   `max_file_size` as in normal writes, fsyncing each file.
   For each new file write its `.hint` file with one hint record
   per kept record, then fsync the hint.
4. Only after all new files and hints are durable: update the
   keydir entries of moved keys to their new locations, delete
   the old immutable files and their hints.
5. Rotate the active file: the old active file becomes immutable
   (its live records stay pointed at by the keydir and will be
   copied by a later merge) and a new empty active file takes an
   id above the merged files. Recovery also performs this rotation
   if it finds the active file is not the highest id, which is
   the signature of a merge interrupted between step 4 and here;
   at that point no post-merge writes exist yet, so scanning in
   id order is still correct.

Failure mid-merge leaves both old and new files on disk; on the
next open, replay deduplicates by keydir position (the new files
have higher ids, so their copies win for moved keys only after
step 4 — if step 4 did not run, the old files still hold the
live copies and the new files are harmless duplicates that a
later merge will clean up). This is safe but not space-free
until the next successful merge; documented, not hidden.

## Divergences from the page (all observable behaviour preserved)

- Keydir does not retain tombstone sentinel entries (page Step 5
  describes the tombstone as max-value metadata in the hash
  table). This implementation removes the key from the keydir
  and stores the tombstone only on disk. Observable behaviour —
  `get` returns nothing, `keys()` omits the key, merge drops it —
  is identical, and it avoids resurrecting deleted keys from a
  retained sentinel.
- No whole-file `Key:Value` rewrite step is kept (Step 1
  placeholder, explicitly superseded by Step 2).
- No RESP/network server (page's "Going Further" only).
- Hint files are produced only by merge, not when an active file
  rotates (the page ties hints to the merge task).
- Default `max_file_size` is 1 MiB, not Riak's 2 GB, so rotation
  is exercisable in tests without huge files; it is a constructor
  argument and the CLI accepts `--max-file-size`.

## What is NOT built

- Multi-process / multi-threaded writes (lock only excludes a
  second opener; in-process thread safety is not provided).
- Compression, TTL/expiry, iterators/snapshots, or a network API.
- Recovery of a record whose CRC fails but whose key is otherwise
  readable — CRC failure means the record is dropped, by design.
