#!/usr/bin/env python3
"""sort - Build Your Own Sort Tool (Coding Challenges #6).

Sorts lines lexicographically (byte order, C locale),
with -u (unique), -R (random sort by hashed keys), and
four selectable algorithms: merge (default), quick,
heap, radix.

Usage:
  ssort.py [-u] [-R] [--algorithm {merge,quick,heap,radix}] [FILE ...]

No file, or file "-", means stdin. Multiple files are
concatenated, then sorted as one list.

Python standard library only, single file. Algorithms
are written by hand (see docs/DESIGN.md); list.sort()
is not used for the actual sorting, except as the
stable carrier for random-sort hash keys.
"""

import argparse
import hashlib
import os
import sys


# --- merge sort (stable) ---

def merge_sort(items):
    if len(items) <= 1:
        return list(items)
    mid = len(items) // 2
    left = merge_sort(items[:mid])
    right = merge_sort(items[mid:])
    out, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            out.append(left[i])
            i += 1
        else:
            out.append(right[j])
            j += 1
    out.extend(left[i:])
    out.extend(right[j:])
    return out


# --- quicksort (iterative, median-of-three) ---

def _median_of_three(items, lo, mid, hi):
    if items[lo] > items[mid]:
        items[lo], items[mid] = items[mid], items[lo]
    if items[mid] > items[hi]:
        items[mid], items[hi] = items[hi], items[mid]
    if items[lo] > items[mid]:
        items[lo], items[mid] = items[mid], items[lo]
    return mid


def quicksort(items):
    items = list(items)
    stack = [(0, len(items) - 1)]
    while stack:
        lo, hi = stack.pop()
        if lo >= hi:
            continue
        mid = (lo + hi) // 2
        pivot_index = _median_of_three(items, lo, mid, hi)
        items[pivot_index], items[hi] = items[hi], items[pivot_index]
        pivot = items[hi]
        i = lo
        for j in range(lo, hi):
            if items[j] <= pivot:
                items[i], items[j] = items[j], items[i]
                i += 1
        items[i], items[hi] = items[hi], items[i]
        stack.append((lo, i - 1))
        stack.append((i + 1, hi))
    return items


# --- heapsort ---

def _sift_down(items, start, end):
    root = start
    while True:
        child = 2 * root + 1
        if child > end:
            break
        if child + 1 <= end and items[child] < items[child + 1]:
            child += 1
        if items[root] < items[child]:
            items[root], items[child] = items[child], items[root]
            root = child
        else:
            break


def heapsort(items):
    items = list(items)
    n = len(items)
    for start in range(n // 2 - 1, -1, -1):
        _sift_down(items, start, n - 1)
    for end in range(n - 1, 0, -1):
        items[0], items[end] = items[end], items[0]
        _sift_down(items, 0, end - 1)
    return items


# --- radix sort (LSD over bytes, stable) ---

def radix_sort(items):
    items = list(items)
    if not items:
        return items
    max_len = max(len(line) for line in items)
    for position in range(max_len - 1, -1, -1):
        # 257 buckets: 0 = "no byte here" (shorter line),
        # 1..256 = byte value + 1.
        counts = [0] * 257
        for line in items:
            bucket = 0 if position >= len(line) else line[position] + 1
            counts[bucket] += 1
        starts = [0] * 257
        total = 0
        for bucket in range(257):
            starts[bucket] = total
            total += counts[bucket]
        out = [None] * len(items)
        for line in items:  # stable: input order within a bucket
            bucket = 0 if position >= len(line) else line[position] + 1
            out[starts[bucket]] = line
            starts[bucket] += 1
        items = out
    return items


ALGORITHMS = {
    "merge": merge_sort,
    "quick": quicksort,
    "heap": heapsort,
    "radix": radix_sort,
}


def dedup(sorted_lines):
    out = []
    for line in sorted_lines:
        if not out or line != out[-1]:
            out.append(line)
    return out


def random_sort(lines, unique):
    """Random permutation, equal lines together (man page
    definition): hash each line with a fresh random salt,
    sort by hash with a stable sort."""
    if unique:
        lines = list(dict.fromkeys(lines))
    salt = os.urandom(16)
    return sorted(lines,
                  key=lambda line: hashlib.sha256(salt + line).digest())


def sort_lines(lines, algorithm="merge", unique=False, random=False):
    if random:
        return random_sort(lines, unique)
    result = ALGORITHMS[algorithm](lines)
    if unique:
        result = dedup(result)
    return result


def read_lines(in_stream):
    """Split a byte stream into lines (no trailing newline
    kept). A final line without a newline still counts;
    a trailing newline does not create an extra line."""
    data = in_stream.read()
    if not data:
        return []
    lines = data.split(b"\n")
    if data.endswith(b"\n"):
        lines.pop()
    return lines


def main(argv):
    parser = argparse.ArgumentParser(
        prog="ssort.py",
        description="Sort lines lexicographically (byte order).")
    parser.add_argument("-u", action="store_true",
                        help="output only the first of each run of "
                             "equal lines")
    parser.add_argument("-R", "--random-sort", action="store_true",
                        help="sort by a random hash of each line, "
                             "equal lines together")
    parser.add_argument("--algorithm", choices=sorted(ALGORITHMS),
                        default="merge",
                        help="sorting algorithm (default: merge)")
    parser.add_argument("files", nargs="*",
                        help="input files, '-' means stdin")
    args = parser.parse_args(argv)

    lines = []
    exit_code = 0
    files = args.files if args.files else ["-"]
    out = sys.stdout.buffer
    for path in files:
        try:
            if path == "-":
                lines.extend(read_lines(sys.stdin.buffer))
            else:
                with open(path, "rb") as f:
                    lines.extend(read_lines(f))
        except OSError as exc:
            print(f"ssort: {path}: {exc.strerror}", file=sys.stderr)
            exit_code = 1
    for line in sort_lines(lines, args.algorithm, args.u,
                           args.random_sort):
        out.write(line + b"\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
