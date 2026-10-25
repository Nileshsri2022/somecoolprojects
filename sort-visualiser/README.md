# sort-visualiser — Terminal Sort Visualiser

Coding Challenges entry 72, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Terminal-based sort visualiser (no GUI): bubble, selection,
insertion, merge and quick sort, each instrumented to emit an
ordered list of comparison/swap/overwrite steps, rendered as
ASCII bar charts in animated, step-through, all-frames, or
stats-only mode. Python 3 standard library only.

**Challenge-page caveat:** no codingchallenges.fyi sort-visualiser
page exists — `challenge-sort-visualiser` and
`challenge-sorting-visualizer` both 404, and web search found no
such page (the site's Sort Tool is a different project, entry 6).
This build follows the task specification instead; see
`docs/SPEC.md` for the full record.

## Usage

```sh
python3 sort_visualiser.py --values 5,3,8 --algorithm bubble
python3 sort_visualiser.py --algorithm quick --size 12 --seed 7
python3 sort_visualiser.py --algorithm merge --size 12 --mode all
python3 sort_visualiser.py --values 5,3,8 --algorithm insertion --mode stats
python3 sort_visualiser.py --values 5,3,8 --algorithm selection --mode step
python3 sort_visualiser.py --list
```

Modes: `animate` (default, `--delay` seconds between frames),
`step` (Enter per frame, EOF stops), `all` (every frame, no
delay), `stats` (summary only). `--values` takes precedence over
`--size`; without `--values`, values are random 1..`--max`
(default 20) with optional `--seed` for reproducibility.

Library use:

```python
from sort_visualiser import sort_with_steps, replay_steps, render_frame
result = sort_with_steps([5, 3, 8], "bubble")
assert replay_steps([5, 3, 8], result.steps) == [3, 5, 8]
print(render_frame(result, 0))
print(result.comparisons, result.swaps)  # counters match the steps
```

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests verify every algorithm sorts correctly (empty, single,
sorted, reverse, duplicates, negatives, fixed random input), that
replaying the emitted steps reproduces the sorted array and every
intermediate snapshot, per-kind step semantics, merge stability,
bubble early exit, rendering, and the CLI in non-interactive modes.
