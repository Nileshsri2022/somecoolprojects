# DESIGN — top

## Layout

Single file `top.py`, Python 3 standard library only:

- `argparse` CLI, `curses` (interactive mode only), `pwd` (UID→name),
  `os`/`time`/`sys` (everything else). No third-party imports.

## Data sources (all under a `proc_root`, default `/proc`)

| Datum | Source | Parsing notes |
|---|---|---|
| Uptime, load | `/proc/uptime`, `/proc/loadavg` | First fields; uptime formatted as `Dd HH:MM` / `HH:MM` / `M min`. |
| CPU totals | `/proc/stat`, first `cpu ` line | Fields: user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice. Idle = idle + iowait. Header percentages are deltas between two samples: `100 × delta_field / delta_total`. |
| Memory/swap | `/proc/meminfo` | `MemTotal`, `MemFree`, `MemAvailable`, `Buffers`, `Cached`, `SwapTotal`, `SwapFree` (kB). `used = total − free − buffers − cached`; buff/cache = buffers + cached. |
| Per-process | `/proc/<pid>/stat` | Numeric directory names only. `comm` may contain spaces or parentheses, so parse as: everything between the first `(` and the last `)` is `comm`; the fields after `)` are numbered from field 3 (`state`). Needed fields: state (3), ppid (4), utime (14), stime (15), priority (18), nice (19), num_threads (20), vsize (23), rss pages (24). `CLK_TCK` from `os.sysconf('SC_CLK_TCK')`, page size from `os.sysconf('SC_PAGE_SIZE')`. |
| Shared memory | `/proc/<pid>/statm` | Third field = shared pages × page size → SHR KiB. Missing `statm` → SHR 0. |
| Username | `pwd.getpwuid(uid)` | UID from `/proc/<pid>/status` `Uid:` line. Unresolvable UID → the numeric UID as a string. If `status` cannot be read, uid is `None` and user renders as `?` (UID 0 is never assumed). |

Processes that vanish between directory listing and file reads are
skipped silently (a normal race in a live `/proc`), never fatal.

## Snapshot model

```python
@dataclass Process: pid, user, pr, ni, virt_kb, res_kb, shr_kb,
    state, cpu_ticks, cpu_percent, mem_percent, time_seconds, command
```

- `sample_processes(proc_root)` reads one full table (cpu_percent 0).
- `snapshot(proc_root, delay)`:
  1. reads CPU totals + process table (sample 1);
  2. if `delay > 0`, sleeps `delay`, then reads CPU totals + process
     table (sample 2); `%CPU` for each PID present in both samples is
     `(ticks2 − ticks1) / (CLK_TCK × delay) × 100`, clamped at ≥ 0;
     PIDs appearing only in sample 2 get `0.0`;
  3. if `delay == 0`, sample 2 is sample 1 and every `%CPU` is `0.0`
     (no interval → no rate; never fabricated).
  4. header CPU percentages come from the same two CPU-total samples;
     with `delay == 0` the delta is zero, so the header reports
     `100.0 id` and `0.0` elsewhere (the only honest degenerate value).
- `%MEM` needs MemTotal, so it is filled in at render/snapshot time
  from the same `meminfo` read.

This two-sample design is what makes `%CPU` headlessly testable: tests
build two fake trees (or one tree read twice with a zero delay) and
check the arithmetic exactly, without depending on a live scheduler.

## Sorting

`SORT_KEYS` maps a key name to `(attribute, reverse)`:

- `pid` → pid, ascending; `user` → user, ascending;
  `command` → command, ascending;
- `cpu` → cpu_percent, descending; `mem` → mem_percent, descending;
  `time` → time_seconds, descending; `virt` → virt_kb, descending;
  `res` → res_kb, descending.

Ties break by PID ascending (stable secondary key), so output order
is fully deterministic for a given table.

## Rendering (batch)

```
top - 23:01:44 up 1:23,  2 users,  load average: 0.10, 0.20, 0.30
Tasks:  42 total,   1 running,  41 sleeping,   0 stopped,   0 zombie
%Cpu(s):  1.2 us,  0.3 sy,  0.0 ni, 98.5 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st
MiB Mem :   7936.0 total,   1234.0 free,   3456.0 used,   3246.0 buff/cache
MiB Swap:      0.0 total,      0.0 free,      0.0 used.      0.0 avail Mem
    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
      1 root      20   0  167900  12936   8488 S   0.0   0.2   0:01.15 systemd
```

- Header widths mirror real `top` closely enough to be recognisable;
  exact column alignment is tested against the renderer's own format
  string, not byte-compared to system `top` (live values differ).
- `TIME+` formatting: under 1 hour → `M:SS.cc` (centiseconds);
  1 hour and over → `H:MM:SS`.
- The user count in the header is the distinct-UID count (see SPEC
  divergence 4).

## Interactive mode

`run_interactive` wraps the same `snapshot` + `format_snapshot`
pipeline in a `curses` loop: each iteration draws the formatted text,
waits up to `delay` seconds for a key (`getch` with timeout), and
applies `q`/`P`/`M`/`N`/`T`/`k` (guarded message, see SPEC). Curses
failures (no TTY, missing terminfo) fall back to one batch snapshot
with a warning on stderr rather than crashing — but the normal path
when stdout is not a TTY is batch mode, chosen before curses starts.

## Errors

- Missing/unreadable `proc_root`: `SnapshotError`, CLI exit 2.
- Unknown sort key, bad `--pid` value, negative `--limit`/`-n`:
  `argparse` error, exit 2.
- A single unreadable process entry never aborts a snapshot.
