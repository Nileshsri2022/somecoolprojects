# DESIGN — Sort Visualiser

## Assumptions (stated before coding, per ponytail rules)

- Values are integers. Sorting works for any integers (including
  negatives and duplicates); bar scaling assumes the chart reads best
  for non-negative values (the CLI default range is 1..max).
- Bar scaling: bar length = round(value / max_value * max_width) for
  positive values, 0 for values <= 0, where max_value is the largest
  value in the frame (0 if the frame is empty or all <= 0). The value
  itself is always printed, so a zero/negative bar is still legible.
- The step list always starts with the algorithm's first comparison
  (there is no separate "initial" snapshot step) and always ends with
  exactly one `done` step whose snapshot is the sorted array.
- Highlighting is a marker column, not colour: `*` for a highlighted
  index, ` ` otherwise. This keeps rendered output testable.

## Algorithm choices

- Bubble: classic adjacent passes, shrinking the inner loop by the
  pass number, early exit on a pass with no swaps. Emits `compare`
  then, only when out of order, `swap`.
- Selection: each pass scans the unsorted suffix for the minimum and
  swaps it into place. Emits `compare` per scan comparison, and a
  `swap` only when the minimum index differs from the pass index
  (a self-swap would be a no-op step and is not emitted).
- Insertion: implemented as adjacent swaps (each element bubbles left
  while it is smaller than its predecessor), rather than the
  shift-and-insert form. Reason: the step-replay invariant in SPEC §4
  is then swap-only for this algorithm, exactly like bubble/selection,
  and each swap is directly visible as a bar-chart frame. The sorted
  result and comparison count are the same order as the shift form;
  the number of emitted moves differs by construction and is not
  claimed to match the shift form.
- Merge: top-down, stable (left element wins ties), merging into a
  temporary copy and writing back one element at a time. Emits
  `compare` per element choice and `overwrite` per write-back. The
  temporary array is never exposed as a step; only write-backs are,
  which is what makes replay (SPEC §4) work.
- Quick: Lomuto partition with the last element as pivot. Emits a
  `pivot` step when a partition starts, `compare` per element-vs-pivot
  comparison, and `swap` only for real exchanges (the final pivot
  placement included). Pivot choice is deliberately the simplest
  textbook one; no median-of-three, so worst-case behaviour on sorted
  input is quadratic — documented, not hidden.

## Step / result model

```python
Step(kind, indices, array, value=None)
# kind: "compare" | "swap" | "overwrite" | "pivot" | "done"
# indices: tuple of highlighted indices (1 for overwrite/pivot)
# array: list snapshot AFTER the step
# value: for "overwrite" only, the value written (== array[index])
```

`sort_with_steps(values, algorithm)` returns a `SortResult` with
`sorted_values`, `steps`, `comparisons`, `swaps`, `overwrites`.
Counters count emitted steps of the matching kind, so counters and
the step list can never disagree. `replay_steps(values, steps)`
applies mutating steps in order and returns the resulting list; it
is the function the tests use for the consistency invariant.

## Rendering

`render_array(values, highlight=(), max_width=40)` returns one line
per element: `"{marker} {index:>2} {value:>3} {bar}"`. A frame is
`render_array` plus a header line (`algorithm, step i/n, kind,
indices`) produced by `render_frame(result, step_index)`.

## CLI

`argparse` only. `animate` clears the screen between frames with
ANSI escapes and sleeps `--delay` (default 0.2s); `step` reads one
line from stdin per frame (EOF ends the walk early, printing the
remaining summary); `all` prints all frames; `stats` prints only
the summary. `--seed` seeds `random.Random` for reproducibility.
Exit codes: 0 success, 2 argument/validation error (argparse or
`ValueError` caught in `main`).

## Divergences from the (absent) challenge page

None can be measured against a page that does not exist (see
SPEC.md). The deliberate choices above — insertion-as-swaps,
Lomuto/last-element quicksort pivot, marker-based (not coloured)
highlighting — are the only places this build picks a variant where
the task text left the variant open, and each is stated here with
its reason.
