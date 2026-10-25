# top — Build Your Own Top

Coding Challenges "Build Your Own Top", worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A live process monitor in Python 3, standard library only. It reads
process data from `/proc` — never `psutil`, never shelling out to
`top`/`ps`.

## Usage

```sh
python3 top.py -b -n 1 -d 0            # one batch snapshot (pipeable)
python3 top.py -b -n 3 -d 1            # three snapshots, 1 s apart
python3 top.py -b -n 1 -d 0 -o cpu     # sort by %CPU, descending
python3 top.py -b -n 1 -d 0 -u root    # only root's processes
python3 top.py -b -n 1 -d 0 --limit 10 # top 10 rows only
python3 top.py                         # interactive curses UI (on a TTY)
```

Output (batch):

```
top - 17:42:06 up 47 min, 1 user, load average: 4.77, 4.25, 2.68
Tasks:  12 total,   1 running,  11 sleeping,   0 stopped,   0 zombie
%Cpu(s):   0.0 us,   0.0 sy,   0.0 ni, 100.0 id,   0.0 wa,   0.0 hi,   0.0 si,   0.0 st
MiB Mem :   7935.1 total,    264.4 free,   7136.3 used,    534.4 buff/cache
MiB Swap:      0.0 total,      0.0 free,      0.0 used.    434.8 avail Mem
    PID USER      PR  NI     VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
      1 root      20   0    20868   4720   2048 S   0.0   0.1   0:00.24 systemd
```

## Options

- `-b`/`--batch`: plain-text output, no curses.
- `-n`/`--iterations`: number of refreshes (default: until stopped).
- `-d`/`--delay`: seconds between refreshes (default 3.0). `%CPU` is
  measured over this interval; with `-d 0` it is honestly reported
  as `0.0` (no interval, no rate).
- `-o`/`--sort`: `pid` (default, per the challenge page's quoted man
  page), `cpu`, `mem`, `time`, `virt`, `res`, `command`, `user`.
- `-u`/`--user`, `-p`/`--pid`, `--limit`: filtering / row limit.
- Interactive keys (curses mode): `q` quit, `P` sort CPU, `M` sort
  memory, `N` sort PID, `T` sort time.

## Columns and limits

Columns: `PID USER PR NI VIRT RES SHR S %CPU %MEM TIME+ COMMAND`
(`VIRT`/`RES`/`SHR` in KiB; `COMMAND` is the short name from
`/proc/<pid>/stat`). Platform: Linux only — without `/proc` the
program exits with an error (exit 2). The header user count is the
number of distinct UIDs among listed processes, not a utmp login count.

**Kill/renice are NOT built.** There is no `--kill` flag and no
signal-sending code; in interactive mode `k` only shows
"kill/renice not supported in this build". Interactive curses behaviour
is not claimed as headlessly tested — see `docs/TEST_PLAN.md`.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

41 tests, all against fake `/proc` trees (plus one live smoke test
that only checks exit code and header presence). Remove
`__pycache__` directories after running tests if they reappear.

## Files

- `top.py` — monitor: `/proc` parsing, snapshots, sorting, rendering,
  batch + curses modes.
- `docs/SPEC.md` — challenge spec, resolved URL, divergences, scope limits.
- `docs/DESIGN.md` — data sources, snapshot model, sorting, rendering.
- `docs/TEST_PLAN.md` — test coverage and what is not tested headlessly.
- `tests/test_top.py` — the test suite.
