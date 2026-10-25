#!/usr/bin/env python3
"""Bitcask: a log-structured hash table (codingchallenges.fyi).

See docs/SPEC.md for the on-disk format. Standard library only.

Record (little-endian):
    CRC-32 (4) | timestamp (4) | key size (4) | value size (4)
    | key | value
CRC-32 (zlib.crc32) covers everything after the CRC field.
A tombstone record has value size 0xFFFFFFFF and no value bytes.
Files are named cask.<id> in the database directory; the highest
id is the active (appendable) file. Merge writes cask.<id>.hint
files beside the new files.
"""

import os
import struct
import sys
import time
import zlib

try:
    import fcntl
except ImportError:  # non-POSIX platforms: lock becomes advisory-free
    fcntl = None

HEADER = struct.Struct("<IIII")  # crc, timestamp, key_size, value_size
HINT = struct.Struct("<IIIQ")    # timestamp, key_size, value_size, value_pos
TOMBSTONE = 0xFFFFFFFF
DEFAULT_MAX_FILE_SIZE = 1024 * 1024


def _to_bytes(value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError("key/value must be str or bytes")


def _record(timestamp, key, value):
    """Encode a record (value=None means tombstone). Returns bytes."""
    if value is None:
        body = struct.pack("<III", timestamp, len(key), TOMBSTONE)
        crc = zlib.crc32(body + key) & 0xFFFFFFFF
        return struct.pack("<I", crc) + body + key
    body = struct.pack("<III", timestamp, len(key), len(value))
    crc = zlib.crc32(body + key + value) & 0xFFFFFFFF
    return struct.pack("<I", crc) + body + key + value


def _parse_records(path):
    """Yield (offset, timestamp, key, value_or_None, value_offset, end).

    Stops (without raising) at the first truncated header, truncated
    body, impossible size, or CRC mismatch. `end` is the offset just
    past the last valid record; a caller may truncate the active
    file at `end` to discard a torn tail. `value_or_None` is None
    for a tombstone.
    """
    offset = 0
    with open(path, "rb") as f:
        data = f.read()
    size = len(data)
    while offset + HEADER.size <= size:
        crc, timestamp, key_size, value_size = HEADER.unpack_from(data, offset)
        if value_size == TOMBSTONE:
            value_len = 0
        else:
            value_len = value_size
        end = offset + HEADER.size + key_size + value_len
        if end > size:
            break
        body = data[offset + 4:end]
        if (zlib.crc32(body) & 0xFFFFFFFF) != crc:
            break
        key_start = offset + HEADER.size
        key = data[key_start:key_start + key_size]
        if value_size == TOMBSTONE:
            yield offset, timestamp, key, None, None, end
        else:
            value = data[key_start + key_size:end]
            yield offset, timestamp, key, value, key_start + key_size, end
        offset = end
    # Final offset reached is implicit: callers recompute from yields.


def _scan_file(path):
    """Return (entries, valid_end) for a data file.

    entries: list of (offset, timestamp, key, value_or_None, value_offset)
    valid_end: offset past the last valid record.
    """
    entries = []
    valid_end = 0
    for offset, timestamp, key, value, value_offset, end in _parse_records(path):
        entries.append((offset, timestamp, key, value, value_offset))
        valid_end = end
    return entries, valid_end


def _parse_hints(path):
    """Parse a hint file; return list of entries or None if malformed.

    Entry: (timestamp, key, value_size, value_pos). Any truncation,
    impossible size/offset, or trailing bytes makes the whole hint
    unusable (caller falls back to scanning the data file).
    """
    with open(path, "rb") as f:
        data = f.read()
    entries = []
    offset = 0
    while offset < len(data):
        if offset + HINT.size > len(data):
            return None
        timestamp, key_size, value_size, value_pos = HINT.unpack_from(data, offset)
        offset += HINT.size
        if offset + key_size > len(data):
            return None
        key = data[offset:offset + key_size]
        offset += key_size
        entries.append((timestamp, key, value_size, value_pos))
    return entries


def _write_hint(path, entries):
    """entries: (timestamp, key, value_size, value_pos)."""
    with open(path, "wb") as f:
        for timestamp, key, value_size, value_pos in entries:
            f.write(HINT.pack(timestamp, len(key), value_size, value_pos))
            f.write(key)
        f.flush()
        os.fsync(f.fileno())


class Bitcask:
    """A Bitcask database rooted at a directory."""

    def __init__(self, directory, max_file_size=DEFAULT_MAX_FILE_SIZE):
        self.directory = os.path.abspath(directory)
        self.max_file_size = max_file_size
        self.keydir = {}  # key -> (file_id, value_offset, value_size, timestamp)
        self._closed = False
        self._active_id = None
        self._active = None
        self._lock_file = None
        os.makedirs(self.directory, exist_ok=True)
        self._acquire_lock()
        try:
            self._recover()
        except Exception:
            self._release_lock()
            raise

    # -- locking -----------------------------------------------------
    def _acquire_lock(self):
        lock_path = os.path.join(self.directory, "bitcask.lock")
        self._lock_file = open(lock_path, "a+b")
        if fcntl is not None:
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self._lock_file.close()
                self._lock_file = None
                raise RuntimeError(
                    "database is already open by another process"
                ) from None

    def _release_lock(self):
        if self._lock_file is not None:
            try:
                if fcntl is not None:
                    fcntl.flock(self._lock_file, fcntl.LOCK_UN)
            finally:
                self._lock_file.close()
                self._lock_file = None

    # -- paths -------------------------------------------------------
    def _data_path(self, file_id):
        return os.path.join(self.directory, "cask.%d" % file_id)

    def _hint_path(self, file_id):
        return self._data_path(file_id) + ".hint"

    def _list_file_ids(self):
        ids = []
        for name in os.listdir(self.directory):
            if name.startswith("cask.") and not name.endswith(".hint"):
                rest = name[len("cask."):]
                if rest.isdigit():
                    ids.append(int(rest))
        return sorted(ids)

    # -- recovery ----------------------------------------------------
    def _write_active(self):
        path = os.path.join(self.directory, "ACTIVE")
        with open(path, "w") as f:
            f.write(str(self._active_id))
            f.flush()
            os.fsync(f.fileno())

    def _recover(self):
        ids = self._list_file_ids()
        if not ids:
            self._active_id = 0
            self._active = open(self._data_path(0), "ab")
            self._write_active()
            return
        # The active file is recorded in ACTIVE. Merged files get ids
        # above the active id, so "highest id" is NOT the active file
        # after a merge; fall back to highest id only if ACTIVE is
        # missing (e.g. a database created before this was added).
        self._active_id = ids[-1]
        try:
            with open(os.path.join(self.directory, "ACTIVE")) as f:
                recorded = int(f.read().strip())
            if recorded in ids:
                self._active_id = recorded
        except (OSError, ValueError):
            pass
        # Scan in id order. This is chronological order provided the
        # merge invariant holds (active file has the highest id; see
        # merge()). If a previous merge was interrupted before its
        # final rotation, the active file is not the highest id; the
        # scan is still correct at this point (no post-merge writes
        # exist yet), and the rotation below restores the invariant
        # before any new write can happen.
        for file_id in ids:
            path = self._data_path(file_id)
            is_active = file_id == self._active_id
            entries = None
            if not is_active:
                hint_path = self._hint_path(file_id)
                if os.path.exists(hint_path):
                    entries = _parse_hints(hint_path)
                    if entries is not None:
                        # Validate hint offsets against the data file.
                        if not self._hints_valid(path, entries):
                            entries = None
            if entries is not None:
                for timestamp, key, value_size, value_pos in entries:
                    self.keydir[key] = (file_id, value_pos, value_size, timestamp)
            else:
                scanned, valid_end = _scan_file(path)
                for offset, timestamp, key, value, value_offset in scanned:
                    if value is None:  # tombstone
                        self.keydir.pop(key, None)
                    else:
                        self.keydir[key] = (file_id, value_offset,
                                            len(value), timestamp)
                if is_active:
                    file_size = os.path.getsize(path)
                    if valid_end < file_size:
                        # Discard torn/corrupt tail so appends overwrite it.
                        with open(path, "r+b") as f:
                            f.truncate(valid_end)
        self._active = open(self._data_path(self._active_id), "ab")
        if self._active_id != max(ids):
            # Interrupted merge: merged files sit above the active
            # file. Rotate now so future writes go to a new highest
            # file and id order stays chronological.
            self._rotate()

    @staticmethod
    def _hints_valid(path, entries):
        try:
            size = os.path.getsize(path)
        except OSError:
            return False
        for _timestamp, _key, value_size, value_pos in entries:
            if value_pos + value_size > size:
                return False
        return True

    # -- internals ---------------------------------------------------
    def _check_open(self):
        if self._closed:
            raise ValueError("database is closed")

    def _append(self, record):
        """Append a record; return (offset, file_id it was written to)."""
        file_id = self._active_id
        self._active.seek(0, os.SEEK_END)
        offset = self._active.tell()
        self._active.write(record)
        self._active.flush()
        os.fsync(self._active.fileno())
        if self._active.tell() > self.max_file_size:
            self._rotate()
        return offset, file_id

    def _rotate(self):
        self._active.close()
        # Max+1, not active+1: merged files may already hold ids
        # above the active id, and reusing one would clobber it.
        existing = self._list_file_ids()
        self._active_id = (max(existing) + 1) if existing else 0
        self._active = open(self._data_path(self._active_id), "ab")
        self._write_active()

    # -- public API --------------------------------------------------
    def put(self, key, value):
        self._check_open()
        key = _to_bytes(key)
        value = _to_bytes(value)
        timestamp = int(time.time())
        record = _record(timestamp, key, value)
        offset, file_id = self._append(record)
        value_offset = offset + HEADER.size + len(key)
        self.keydir[key] = (file_id, value_offset, len(value), timestamp)
        return None

    def get(self, key):
        self._check_open()
        key = _to_bytes(key)
        entry = self.keydir.get(key)
        if entry is None:
            return None
        file_id, value_offset, value_size, _timestamp = entry
        with open(self._data_path(file_id), "rb") as f:
            f.seek(value_offset)
            data = f.read(value_size)
        if len(data) != value_size:
            return None
        return data

    def delete(self, key):
        self._check_open()
        key = _to_bytes(key)
        timestamp = int(time.time())
        self._append(_record(timestamp, key, None))
        self.keydir.pop(key, None)

    def keys(self):
        self._check_open()
        return sorted(self.keydir)

    def merge(self):
        """Compact all immutable files, keeping only live records."""
        self._check_open()
        ids = self._list_file_ids()
        immutable = [i for i in ids if i != self._active_id]
        if not immutable:
            return
        # Collect live records from immutable files, in file order.
        live = []  # (key, timestamp, value_bytes)
        for file_id in immutable:
            scanned, _end = _scan_file(self._data_path(file_id))
            for offset, timestamp, key, value, _value_offset in scanned:
                if value is None:
                    continue
                current = self.keydir.get(key)
                if current is not None and current[0] == file_id \
                        and current[1] == _value_offset:
                    live.append((key, timestamp, value))
        if not live:
            # Nothing live: just delete the old files.
            for file_id in immutable:
                self._remove_file(file_id)
            return
        next_id = max(ids) + 1
        new_files = []  # (file_id, [(timestamp, key, value_size, value_pos)])
        cur_id = next_id
        cur_path = self._data_path(cur_id)
        cur = open(cur_path, "wb")
        cur_hints = []
        cur_size = 0
        for key, timestamp, value in live:
            record = _record(timestamp, key, value)
            if cur_size > 0 and cur_size + len(record) > self.max_file_size:
                cur.flush()
                os.fsync(cur.fileno())
                cur.close()
                _write_hint(self._hint_path(cur_id), cur_hints)
                new_files.append((cur_id, cur_hints))
                cur_id += 1
                cur_path = self._data_path(cur_id)
                cur = open(cur_path, "wb")
                cur_hints = []
                cur_size = 0
            value_pos = cur_size + HEADER.size + len(key)
            cur.write(record)
            cur_hints.append((timestamp, key, len(value), value_pos))
            cur_size += len(record)
        cur.flush()
        os.fsync(cur.fileno())
        cur.close()
        _write_hint(self._hint_path(cur_id), cur_hints)
        new_files.append((cur_id, cur_hints))
        # Update keydir to new locations, then delete old files.
        new_locations = {}
        for file_id, hints in new_files:
            for timestamp, key, value_size, value_pos in hints:
                new_locations[key] = (file_id, value_pos, value_size, timestamp)
        for key, loc in new_locations.items():
            self.keydir[key] = loc
        for file_id in immutable:
            self._remove_file(file_id)
        # Final rotation: the old active file becomes immutable and a
        # new active file takes an id above the merged files. Without
        # this, post-merge writes to the old active file would sort
        # below the merged copies on reopen and lose to them.
        self._rotate()

    def _remove_file(self, file_id):
        for path in (self._data_path(file_id), self._hint_path(file_id)):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._active is not None:
                self._active.close()
                self._active = None
        finally:
            self._release_lock()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def main(argv):
    if len(argv) < 2 or argv[0] != "-db":
        print("usage: bitcask.py -db DIR [--max-file-size N] "
              "set KEY VALUE | get KEY | del KEY | merge | list",
              file=sys.stderr)
        return 2
    directory = argv[1]
    rest = argv[2:]
    max_file_size = DEFAULT_MAX_FILE_SIZE
    if rest[:1] == ["--max-file-size"]:
        if len(rest) < 3:
            print("missing value for --max-file-size", file=sys.stderr)
            return 2
        max_file_size = int(rest[1])
        rest = rest[2:]
    if not rest:
        print("missing command", file=sys.stderr)
        return 2
    cmd, args = rest[0], rest[1:]
    try:
        db = Bitcask(directory, max_file_size=max_file_size)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        if cmd == "set" and len(args) == 2:
            db.put(args[0], args[1])
        elif cmd == "get" and len(args) == 1:
            value = db.get(args[0])
            print(value.decode("utf-8", "replace") if value is not None else "(nil)")
        elif cmd in ("del", "delete") and len(args) == 1:
            db.delete(args[0])
        elif cmd == "merge" and not args:
            db.merge()
        elif cmd == "list" and not args:
            for key in db.keys():
                print(key.decode("utf-8", "replace"))
        else:
            print("unknown or malformed command: %s" % cmd, file=sys.stderr)
            return 2
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
