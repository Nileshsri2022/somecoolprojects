# Bitcask — TEST PLAN

Run from the project directory:

```
python3 -m unittest discover -s tests -v
```

All tests use `tempfile.TemporaryDirectory` — no test touches the
real repo, the user's home, or a fixed path. No network.

## Cases (all in tests/test_bitcask.py)

Library level:

1. Put then get returns the value; get of a missing key is None.
2. Overwrite: a second put wins, and the old value is gone.
3. Empty value is retrievable (distinguishes empty from deleted).
4. Binary keys/values (non-UTF-8 bytes) round-trip.
5. Delete: get returns None afterwards; deleting a missing key
   is a no-op; re-put after delete works.
6. Rotation: with a tiny `max_file_size`, puts span multiple
   `cask.<id>` files and every key is still readable (checks
   Step 4's multi-file requirement).
7. Reopen after close: close, reopen the same directory, all live
   keys read back, deleted keys stay deleted (crash-recovery
   replay path via clean close).
8. Crash recovery: append garbage / a torn partial record to the
   active log after close, reopen — old keys survive, the torn
   tail is truncated, and new puts after reopen are readable
   (i.e. the garbage does not corrupt later appends).
9. CRC corruption: flip a byte in a value, reopen — the corrupted
   record is dropped (get returns None / the previous value if
   the key had an older live copy) and later puts still work.
10. Tombstone survives reopen: put, delete, close, reopen —
    get is still None (replay of the tombstone, not just the
    in-memory removal).
11. Merge: with several immutable files holding overwritten and
    deleted keys, merge keeps every live value, drops dead keys,
    deletes the old immutable files, leaves the active file
    alone, and values survive a reopen after merge.
12. Merge writes hint files, and reopening after merge (which
    replays via hints for immutable files) returns all values.
13. Merge with no immutable files is a no-op (no crash, no files
    deleted).
14. Second opener is rejected while the first is open (lock).
15. Use after close raises; close is idempotent; context manager
    closes on exit.

17. Post-merge overwrite: after a merge, overwriting a merged key
    and forcing a rotation still returns the new value, including
    after a reopen (guards the merged-id vs active-id ordering).

CLI level (via `subprocess`, temp directory):

16. `set` then `get` prints the value; `get` of a missing key
    prints `(nil)`; `del` then `get` prints `(nil)`; `merge`
    exits 0; `list` shows live keys only.

Success criteria: every test passes; no test writes outside its
temporary directory; the suite runs in seconds with stdlib only.
