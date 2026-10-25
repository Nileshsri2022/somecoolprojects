#!/usr/bin/env python3
"""ccdupe — find duplicate files to free storage space.

Build Your Own Duplicate File Finder (codingchallenges.fyi):
  https://codingchallenges.fyi/challenges/challenge-duplicate-files/

Pipeline (cheap filter first, expensive check last):
  walk tree -> group by size -> group by MD5 -> byte-by-byte confirm.

Default output is one line per confirmed duplicate group:
  Duplicates: file1 subdir/duplicateoffile1

Modes: --list (Step 1), --potential (Step 2, size only),
--probable (Step 3, MD5 only), default (Step 4, confirmed).
--minsize N is Step 5; --delete is the Step 6 interactive prompt.

Deletion is strictly opt-in: without --delete nothing is deleted.
Python 3 standard library only.
"""

import argparse
import hashlib
import json
import os
import sys

CHUNK_SIZE = 65536


def warn(message):
    print("ccdupe: warning: " + message, file=sys.stderr)


# ---------------------------------------------------------------- walk

def collect_files(root, follow_symlinks=False):
    """Return sorted relative paths of regular files under root.

    Symlinks are skipped unless follow_symlinks is set. When following
    symlinks, directory (device, inode) pairs already visited are not
    descended into again, so symlink cycles terminate.
    """
    found = []
    visited_dirs = set()

    def walk(dir_abs, dir_rel):
        try:
            with os.scandir(dir_abs) as entries:
                entries = sorted(entries, key=lambda e: e.name)
        except OSError as exc:
            warn("cannot list directory %s: %s" % (dir_rel or ".", exc))
            return
        for entry in entries:
            rel = entry.name if not dir_rel else dir_rel + "/" + entry.name
            try:
                if entry.is_symlink():
                    if not follow_symlinks:
                        continue
                    # Follow it: stat the target.
                    try:
                        st = entry.stat(follow_symlinks=True)
                    except OSError as exc:
                        warn("cannot follow symlink %s: %s" % (rel, exc))
                        continue
                    if os.path.isdir(entry.path):
                        key = (st.st_dev, st.st_ino)
                        if key in visited_dirs:
                            continue
                        visited_dirs.add(key)
                        walk(entry.path, rel)
                    elif os.path.isfile(entry.path):
                        found.append(rel)
                    continue
                if entry.is_dir(follow_symlinks=False):
                    try:
                        st = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    key = (st.st_dev, st.st_ino)
                    if key in visited_dirs:
                        continue
                    visited_dirs.add(key)
                    walk(entry.path, rel)
                elif entry.is_file(follow_symlinks=False):
                    found.append(rel)
            except OSError as exc:
                warn("cannot inspect %s: %s" % (rel, exc))
                continue

    try:
        root_st = os.stat(root)
    except OSError:
        root_st = None
    if root_st is not None:
        visited_dirs.add((root_st.st_dev, root_st.st_ino))
    walk(root, "")
    return sorted(found)


# ---------------------------------------------------------------- stages

def group_by_size(root, files, min_size=0):
    """Group files by size; keep groups of 2+ at or above min_size."""
    groups = {}
    for rel in files:
        try:
            size = os.path.getsize(os.path.join(root, rel))
        except OSError as exc:
            warn("cannot stat %s: %s" % (rel, exc))
            continue
        if size < min_size:
            continue
        groups.setdefault(size, []).append(rel)
    return {size: sorted(paths) for size, paths in groups.items()
            if len(paths) >= 2}


def file_md5(path):
    """MD5 hex digest of a file, streamed; None on read error.

    MD5 is used only as a fast content fingerprint, never for
    security (per the challenge page); Step 4's byte compare is the
    authoritative check.
    """
    try:
        md5 = hashlib.md5(usedforsecurity=False)
    except TypeError:  # older Python without the keyword
        md5 = hashlib.md5()
    try:
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                md5.update(chunk)
    except OSError:
        return None
    return md5.hexdigest()


def group_by_md5(root, size_groups):
    """Within each size group, group by MD5; keep groups of 2+."""
    result = []
    for size in sorted(size_groups):
        by_hash = {}
        for rel in size_groups[size]:
            digest = file_md5(os.path.join(root, rel))
            if digest is None:
                warn("cannot read %s: skipped" % rel)
                continue
            by_hash.setdefault(digest, []).append(rel)
        for digest in sorted(by_hash):
            paths = sorted(by_hash[digest])
            if len(paths) >= 2:
                result.append(paths)
    return result


def files_identical(path_a, path_b):
    """True iff both files have identical bytes (chunk-wise)."""
    try:
        if os.path.getsize(path_a) != os.path.getsize(path_b):
            return False
    except OSError:
        return False
    try:
        with open(path_a, "rb") as fa, open(path_b, "rb") as fb:
            while True:
                chunk_a = fa.read(CHUNK_SIZE)
                chunk_b = fb.read(CHUNK_SIZE)
                if chunk_a != chunk_b:
                    return False
                if not chunk_a:
                    return True
    except OSError:
        return False


def confirm_duplicates(root, md5_groups):
    """Byte-compare each MD5 group against its first file."""
    confirmed = []
    for group in md5_groups:
        first = os.path.join(root, group[0])
        keep = [group[0]]
        for rel in group[1:]:
            if files_identical(first, os.path.join(root, rel)):
                keep.append(rel)
        if len(keep) >= 2:
            confirmed.append(sorted(keep))
    confirmed.sort(key=lambda g: g[0])
    return confirmed


def find_potential(root, follow_symlinks=False, min_size=0):
    files = collect_files(root, follow_symlinks)
    groups = group_by_size(root, files, min_size)
    return sorted((sorted(paths) for paths in groups.values()),
                  key=lambda g: g[0])


def find_probable(root, follow_symlinks=False, min_size=0):
    files = collect_files(root, follow_symlinks)
    size_groups = group_by_size(root, files, min_size)
    groups = group_by_md5(root, size_groups)
    groups.sort(key=lambda g: g[0])
    return groups


def find_duplicates(root, follow_symlinks=False, min_size=0):
    files = collect_files(root, follow_symlinks)
    size_groups = group_by_size(root, files, min_size)
    md5_groups = group_by_md5(root, size_groups)
    return confirm_duplicates(root, md5_groups)


# ---------------------------------------------------------------- delete

def prompt_delete(groups, input_fn=input, output=print):
    """Step 6: per group, ask which file to delete.

    A valid number deletes exactly that one file; any other input
    (including EOF) keeps all files and continues. Returns the list
    of deleted relative paths.
    """
    deleted = []
    for group in groups:
        output("Which file should be deleted?")
        for i, rel in enumerate(group, start=1):
            output("  %d) %s" % (i, rel))
        output("  Any other value keeps the file and continues")
        try:
            answer = input_fn().strip()
        except EOFError:
            answer = ""
        try:
            choice = int(answer)
        except ValueError:
            continue
        if 1 <= choice <= len(group):
            victim = group[choice - 1]
            try:
                os.remove(victim)
            except OSError as exc:
                warn("cannot delete %s: %s" % (victim, exc))
                continue
            deleted.append(victim)
            output("Deleted: %s" % victim)
    return deleted


# ---------------------------------------------------------------- CLI

def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="ccdupe",
        description="Find duplicate files (Steps 1-6 of the "
                    "codingchallenges.fyi Duplicate File Finder challenge).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true",
                      help="Step 1: list all files recursively")
    mode.add_argument("--potential", action="store_true",
                      help="Step 2: report same-size groups only")
    mode.add_argument("--probable", action="store_true",
                      help="Step 3: report MD5 groups only")
    parser.add_argument("--minsize", type=int, default=0, metavar="N",
                        help="Step 5: ignore files smaller than N bytes")
    parser.add_argument("--follow-symlinks", action="store_true",
                        help="follow symlinked files and directories")
    parser.add_argument("--json", action="store_true",
                        help="print groups as a JSON array")
    parser.add_argument("--delete", action="store_true",
                        help="Step 6: interactively prompt to delete "
                             "one file per duplicate group")
    parser.add_argument("directory", help="directory to scan")
    args = parser.parse_args(argv)
    if args.minsize < 0:
        parser.error("--minsize must be a non-negative integer")
    if args.delete and (args.list or args.potential or args.probable):
        parser.error("--delete only applies to confirmed duplicates "
                     "(the default mode)")
    if not os.path.isdir(args.directory):
        parser.error("not a directory: %s" % args.directory)
    return args


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = args.directory

    if args.list:
        files = collect_files(root, args.follow_symlinks)
        files = [f for f in files
                 if _size_at_least(root, f, args.minsize)]
        if args.json:
            print(json.dumps(files))
        else:
            for rel in files:
                print(rel)
        return 0

    if args.potential:
        groups = find_potential(root, args.follow_symlinks, args.minsize)
        label = "Potential duplicates"
    elif args.probable:
        groups = find_probable(root, args.follow_symlinks, args.minsize)
        label = "Probable duplicates"
    else:
        groups = find_duplicates(root, args.follow_symlinks, args.minsize)
        label = "Duplicates"

    if args.json:
        print(json.dumps(groups))
    else:
        for group in groups:
            print("%s: %s" % (label, " ".join(group)))

    if args.delete:
        # prompt_delete removes by path; run it from inside root so
        # relative paths resolve, then restore the working directory.
        previous = os.getcwd()
        try:
            os.chdir(root)
            prompt_delete(groups)
        finally:
            os.chdir(previous)
    return 0


def _size_at_least(root, rel, min_size):
    if min_size <= 0:
        return True
    try:
        return os.path.getsize(os.path.join(root, rel)) >= min_size
    except OSError:
        return False


if __name__ == "__main__":
    sys.exit(main())
