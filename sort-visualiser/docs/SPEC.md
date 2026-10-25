# SPEC — Sort Visualiser (somecoolprojects entry 72)

## Challenge-page status (recorded honestly)

- Slug tried first, as instructed:
  `challenge-sort-visualiser` —
  `https://codingchallenges.fyi/challenges/challenge-sort-visualiser/` → **HTTP 404**.
- Second variant tried: `challenge-sorting-visualizer` → **HTTP 404**.
- Web search for a codingchallenges.fyi sort-visualiser page found no such
  page. The site does have a *Sort Tool* challenge (entry 6, already built
  as `sort/`), which is a different project (a Unix `sort` clone, not a
  visualiser). There is therefore **no live codingchallenges.fyi page to
  build this project from**.
- This build instead follows the parent task's specification exactly:
  terminal-based sort visualiser, multiple sorting algorithms instrumented
  to emit comparison/swap steps, rendered as terminal bar charts, with a
  step-through or animated mode, plus non-interactive tests verifying
  sorting correctness and step-sequence consistency. That specification
  is restated below as the requirements; see DESIGN.md for the
  documented choices where the task left details open.

## Requirements

1. Terminal-based only — NO GUI, no web UI, no third-party packages.
   Python 3 standard library only, single main file `sort_visualiser.py`.
2. Algorithms: `bubble`, `selection`, `insertion`, `merge`, `quick`.
   Each must sort correctly, including empty input, single element,
   already-sorted input, reverse-sorted input, and duplicates.
3. Instrumentation: every algorithm emits an ordered list of steps.
   Each step records its kind, the indices it concerns, and a snapshot
   of the array *after* that step. Step kinds:
   - `compare` — two indices compared; array unchanged.
   - `swap` — two indices exchanged; array changed (unless a
     self-swap, which is never emitted).
   - `overwrite` — one index set to a new value (merge write-back only).
   - `pivot` — quicksort pivot index marked; array unchanged.
   - `done` — final step; array is the sorted array.
4. Step consistency (the key invariant, tested): starting from the
   original input and applying only the mutating steps (`swap` and
   `overwrite`, in order) must reproduce the final sorted array.
   Every step snapshot must also equal the array obtained by applying
   all mutating steps up to and including that step.
5. Rendering: each step renders as a terminal bar chart (ASCII):
   one row per element, value plus a `#` bar scaled to the largest
   value, with highlighted indices marked. No ANSI colour is used, so
   output is deterministic and pipeable.
6. Modes:
   - `animate` (default): redraw each frame with a configurable delay.
   - `step`: wait for Enter before each frame (step-through).
   - `all`: print every frame in sequence, no delay, no screen clear.
   - `stats`: print only the summary (algorithm, input, sorted output,
     comparisons, swaps, overwrites, step count).
7. Input: `--values 5,3,8` for an explicit array, or `--size N`
   (default 10) with `--max` (default 20) and `--seed` for a
   reproducible random array. `--algorithm` selects the algorithm
   (default `bubble`); `--list` lists the algorithms and exits.
8. Errors: unknown algorithm, non-integer values, or a negative size
   exit non-zero with a message on stderr. No other failure modes
   are specified; anything else is a bug.

## Out of scope (nothing speculative)

- No GUI, web server, sound, colour themes, or interactive curses UI.
- No file input, no sorting of strings, no algorithm beyond the five.
- No heap/radix/shell sort: the task names bubble, selection,
  insertion, merge, quick "as specified"; those five are the set.
