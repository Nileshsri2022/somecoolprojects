# TEST_PLAN — Sort Visualiser

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

## Cases (all in `tests/test_sort_visualiser.py`, unittest, stdlib only)

1. Correctness, every algorithm (`bubble`, `selection`, `insertion`,
   `merge`, `quick`) against Python's `sorted()` on: empty, single
   element, already sorted, reverse sorted, duplicates, negatives,
   and a fixed pseudo-random list (seed 42, 20 values).
2. Step-sequence consistency, every algorithm, on the same inputs:
   - `replay_steps(original, steps) == sorted(original)`.
   - Every step snapshot equals the array after applying all
     mutating steps up to that step (checked by replaying prefixes).
   - The last step is `done` and its snapshot is the sorted array.
   - `result.sorted_values == sorted(original)`.
   - Counters match the step list: `comparisons` == number of
     `compare` steps, `swaps` == number of `swap` steps,
     `overwrites` == number of `overwrite` steps.
3. Step semantics:
   - A `compare` step never changes the snapshot vs the previous step.
   - A `swap` step differs from the previous snapshot only by
     exchanging its two indices.
   - An `overwrite` step differs only at its index, to its `value`.
   - Merge is stable: equal values keep their relative order (checked
     via decorated (value, original-index) pairs through the merge
     core — see the test's use of `sort_with_steps` on plain values
     plus a stability check on merge with duplicate keys).
   - Bubble stops early: an already-sorted input produces exactly
     n-1 comparisons and 0 swaps.
   - Unknown algorithm raises `ValueError`.
4. Rendering:
   - `render_array` includes every value, uses `#` bars, marks
     highlighted indices with `*` and others with a blank, and
     renders an empty array as an empty string.
   - Bar length scales with value: the largest value gets the full
     `max_width` bar.
   - `render_frame` header names the algorithm, step number, and kind.
5. CLI (via `subprocess`, non-interactive modes only — `step` mode
   is not exercised through a TTY; its input loop is covered by
   feeding EOF on stdin):
   - `--list` exits 0 and names all five algorithms.
   - `--values 5,3,8 --algorithm bubble --mode stats` exits 0 and
     reports the sorted array `3 5 8`.
   - `--mode all` prints a frame per step.
   - Unknown algorithm exits non-zero; non-integer `--values`
     exits non-zero; `--values` and `--size` are not combined
     (explicit values win only if `--size` is left default — see
     README; the test asserts the documented precedence).

## Success criteria

All tests pass; no test touches the network, a TTY, or the clock
except the CLI `--mode all`/`stats` runs, which use no delay.
Manual smoke check (not a test): run the animated mode once and
confirm frames redraw and the final frame is sorted.
