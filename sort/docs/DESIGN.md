# sort — Design

## Assumptions (stated before coding, per ponytail)

1. Language: Python 3, standard library only, single
   file `ssort.py`, same as the previous projects.
2. Lines are bytes, sorted by byte value. Reason:
   byte order is exactly the C-locale order the
   challenge's example shows, it needs no decoding,
   and it makes the radix sort's 256 buckets natural.
3. Algorithms are written by hand, not delegated to
   `list.sort()` — that would defeat step 3, which
   is about learning the algorithms. `list.sort()` is
   used only in tests, as the oracle.
4. Whole input in memory. Reason: the challenge's
   steps are in-memory sorts; external sort is a
   different project and is documented out of scope.

## Algorithm implementations

### Merge sort (default)

```
merge_sort(items):
    if len <= 1: return items
    mid = len // 2
    return merge(merge_sort(left), merge_sort(right))
merge(a, b): walk both with indices, take the smaller
    (<= from the left, for stability), append the rest.
```

Recursion depth is log2(n), so a million lines nest
only ~20 deep — no recursion-limit worry, unlike
naive quicksort.

### Quicksort (iterative)

An explicit stack of (lo, hi) partitions replaces
recursion, so sorted or reverse-sorted input cannot
blow the Python call stack. Partition is Lomuto
with a median-of-three pivot (first, middle, last,
sorted, middle moved to the end as pivot), which
keeps the classic sorted-input worst case away in
practice. Expected O(n log n), in place, not stable
— fine, because dedup compares whole lines.

### Heapsort

Standard: build a max-heap bottom-up (`sift_down`
from n//2 - 1 down to 0), then repeatedly swap the
root to the end and re-heapify the shrinking prefix.
In place, O(n log n), not stable.

### Radix sort (LSD, stable)

```
for position in reversed(range(max_len)):
    counting sort by byte_at(line, position),
    where byte_at returns -1 when the line is shorter
    than position (bucket 0), else the byte + 1
    (buckets 1..256). Stable: equal keys keep order.
```

Processing from the last byte to the first, with
stability at each pass, yields byte-lexicographic
order, including the prefix rule: a shorter line's
missing bytes sort in bucket 0, before any real
byte, at every position past its end.

### Random sort

```
salt = os.urandom(16)          # fresh per run
key(line) = sha256(salt + line).digest()
sorted(lines, key=key)         # Python's stable sort
```

Python's built-in sort is used here only as the
stable carrier for the hash keys — the randomisation
is the hash, as the man page describes. Equal lines
share a hash and, by stability, stay adjacent.
With `-u`, lines are deduped (set, then hash-sorted)
before output, so the result is distinct lines in
random order.

### Unique

After sorting (any algorithm): walk the sorted list,
emit a line only when it differs from the previous
emitted line. For `-R -u`, dedup happens before
hash-sorting (see above), which gives the same set.

## CLI parsing

`argparse` with `-u`, `-R` / `--random-sort`,
`--algorithm` (choices merge/quick/heap/radix,
default merge). Positional files, zero or more;
`-` means stdin; zero files means stdin. Missing
files are reported and skipped, exit 1 at the end.

## File layout

```
sort/
  README.md            usage, examples, how to run tests
  ssort.py             algorithms, random sort, CLI
  docs/
    SPEC.md            challenge spec and sorting order
    DESIGN.md          this file
    TEST_PLAN.md       what is tested, and against what
  tests/
    test_ssort.py      unittest, functions + CLI vs system sort
```

## Success criteria

- `python3 -m unittest discover -s tests -v` passes.
- Each algorithm sorts the same fixtures identically
  to Python's `sorted()` and, for the default, to
  system sort under `LC_ALL=C`.
- `-u` dedups, `-R` permutes with equal keys together,
  `-R -u` gives distinct lines in random order.
- CLI: file, stdin, `-`, multi-file, missing file
  (exit 1, other files still processed).
