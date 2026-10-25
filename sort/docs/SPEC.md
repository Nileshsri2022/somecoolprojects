# sort — Specification (docs first)

Source: Coding Challenges, "Build Your Own Sort Tool"
(https://codingchallenges.fyi/challenges/challenge-sort/)
Target in this repo: `somecoolprojects/sort/`

The Unix `sort` tool, rebuilt from its man-page behaviour
(checked against system GNU sort in the C locale, not
copied from its source). It sorts text files by lines;
a line is a record ending in a newline.

## Challenge steps

1. Open a file, output its lines sorted lexicographically.
   Check: `sort words.txt | uniq | head -n5` gives
   `A, ACTUAL, AGREE, AGREEMENT, AND, ...`.
2. `-u`: unique built into sort — duplicate lines appear
   once. `sort -u words.txt | head -n5` gives the same
   first five lines as step 1's pipeline.
3. Select the sort algorithm. The man page offers radix
   sort, merge sort, quicksort and heapsort. Implement
   as many as you like; this tool implements all four,
   and the `-u` interaction is: dedup after sorting
   (adjacent equal lines), which works for every
   algorithm, stable or not, because dedup compares
   whole lines, not sort stability.
4. Random sort `-R` / `--random-sort`: a random
   permutation of the inputs, except equal keys sort
   together. Per the man page, implemented by hashing
   the input keys and sorting the hash values, with
   the hash function randomised (here: a fresh random
   salt per run). `sort --random-sort -u words.txt`
   gives distinct words in a random order.

## Commands

```
ssort.py [FILE ...]
ssort.py -u [FILE ...]
ssort.py --algorithm {merge,quick,heap,radix} [FILE ...]
ssort.py -R [FILE ...]
ssort.py -R -u [FILE ...]
echo ... | ssort.py
ssort.py - < file
```

The file is named `ssort.py` (not `sort.py`) so it
cannot shadow anything when run from this directory,
following `ccut.py` in the previous project.

## Sorting order

- Lines are compared byte by byte — the C locale order.
  Verified against system sort with `LC_ALL=C`: digits
  sort before uppercase, uppercase before lowercase
  (`10, 2, Apple, apple, banana`). This is not
  locale-aware sorting: in another locale, system sort
  may order punctuation and case differently, and this
  tool will not match it. That is documented, not a
  bug, and the tests pin the C locale for system
  comparisons.
- An empty line sorts before every non-empty line.
- A shorter line that is a prefix of a longer one
  sorts first (`a` before `aa`).
- Every output line ends with `\n`, even if the
  input's last line did not (verified: GNU sort adds
  it, same as `ccut.py`).

## Input

- Zero or more files; no file, or `-` as a file, means
  stdin. Multiple files are concatenated in order,
  then sorted as one list (as system sort does).
- Lines are read as bytes. The challenge says to
  ignore binary files; byte lines keep the tool
  working on UTF-8 text without a decoding step, and
  byte order is the C-locale order above.
- An empty input produces no output. A final line
  without a trailing newline is still a line.

## Algorithms

- `merge`: classic recursive merge sort, stable,
  O(n log n) time, O(n) extra space.
- `quick`: iterative quicksort (explicit stack, no
  recursion-depth risk), median-of-three pivot,
  O(n log n) expected, in place, not stable.
- `heap`: classic heapsort, in place, O(n log n),
  not stable.
- `radix`: least-significant-digit radix sort over
  bytes, stable counting sort per byte position
  (256 buckets, plus a bucket for "no byte here",
  so shorter prefix lines sort first), O(n * maxlen).
- Default algorithm: `merge` (stable, predictable).
- Random sort does not use `--algorithm`: it hashes
  each line with a fresh random salt and sorts by
  hash. Equal lines get equal hashes, so with a
  stable sort they stay together. `-u` with `-R`
  dedups first, then randomises the distinct lines.

## Errors

- Missing/unreadable file: message on stderr, other
  files still processed, exit code 1 at the end
  (same GNU-style convention as `ccut.py`).
- Unknown algorithm: `argparse` rejects it, exit 2.

## Out of scope (ponytail: challenge steps only)

- No `-r` (reverse), no `-n` (numeric), no `-k`
  (key/field), no `-t` (delimiter), no `-f`
  (case-fold), no `-b` (ignore blanks), no locale
  collation, no `-o` (output file), no `-c`
  (check sorted). The challenge never asks for them.
- No external / disk-based sort for files larger
  than memory: the whole input is read and sorted
  in memory, as in the challenge's steps.
