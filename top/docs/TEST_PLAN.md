# TEST_PLAN — top

All tests are `unittest`, in `tests/test_top.py`, run with:

```sh
python3 -m unittest discover -s tests -v
```

Tests never touch the live `/proc` for assertions about values: they
build fake `/proc` trees in `tempfile` directories (meminfo, stat,
loadavg, uptime, and per-PID `stat`/`status`/`statm` files) and pass
them via the `--proc-root` hook or directly to library functions.
One test runs the real binary against the live `/proc` only to assert
it exits 0 and prints a header + table (no value assertions).

## Coverage map

| Area | Cases |
|---|---|
| `/proc/<pid>/stat` parsing | Normal entry; `comm` containing spaces and parentheses; zombie state; malformed line raises/ignored cleanly. |
| `/proc/meminfo` parsing | All keys present; missing `MemAvailable` (avail falls back to free); missing file raises `SnapshotError`. |
| `/proc/stat` CPU totals | Field parsing; idle = idle + iowait; header percentages from a delta; zero-delta header is 100% idle. |
| `%CPU` arithmetic | Two samples, known tick delta and delay → exact percent; PID only in second sample → 0.0; `delay=0` → all 0.0. |
| `%MEM` / `TIME+` | RES/MemTotal ratio; time formatting under and over one hour. |
| Task counts | Running/sleeping/stopped/zombie tallies from state letters (`R`, `S`/`D`/`I`, `T`/`t`, `Z`/`X`). |
| Sorting | Each sort key in the right direction; ties break by PID ascending; unknown key raises `ValueError`. |
| Filtering | `--user` by name and by numeric UID; `--pid` list; `--limit` truncation; non-matching filter yields an empty table but a valid header. |
| Formatting | Header lines present with the expected labels; table header row; a known process renders with its PID, user, state and command on one line. |
| CLI (subprocess, fake proc root) | `-b -n 1 -d 0` exits 0 and prints header + table; unknown sort key exits 2; missing `--proc-root` exits 2; `-b -n 2 -d 0` prints exactly two snapshots. |
| Live smoke | Real `/proc`, `-b -n 1 -d 0`: exit 0, header present (values unchecked). |

## Explicitly NOT tested headlessly

- Interactive curses UI: key handling, screen redraw, and terminal
  resize cannot be exercised without a TTY. The interactive loop is
  deliberately a thin wrapper over the tested snapshot/render
  functions, and its keys are documented in SPEC/README. No claim of
  interactive testing is made.
- Real `%CPU` values on a live system: inherently scheduler-dependent;
  only the arithmetic on controlled samples is asserted.
- Kill/renice: not implemented (guarded message only), so there is
  nothing to test beyond "no signal-sending code path exists" — verified
  by inspection (`grep -n "kill\|os.kill" top.py` returns only the
  guarded message text).
