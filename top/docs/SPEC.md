# SPEC — Build Your Own Top

## Resolved challenge page

- Title: "Build Your Own Top" (Coding Challenges).
- URL: https://codingchallenges.fyi/challenges/challenge-top/
  - Resolved 2026-10-25 via the site's tag index
    (https://codingchallenges.fyi/challenges/tags, which lists `cli` and
    `unix`) plus a web search for "codingchallenges.fyi top challenge",
    whose first result was exactly this URL. The URL was NOT guessed.
  - Retrieval caveat (honest): a direct full-page text fetch of the
    challenge page was rate-limited (HTTP 429 from the fetch service) on
    2026-10-25, so the step-by-step body beyond what the search result
    exposed could not be re-read verbatim during this build. What the
    search result did expose, and what this spec is built on, is quoted
    below. No step text has been invented to fill the gap: anything not
    exposed is recorded under "Not verified / not built" rather than
    claimed as a page requirement.

## What the page says (as exposed by the search result)

> "This challenge is to build your own version of the command line tool
> top."

> "The Unix command line tools are a great metaphor for good software
> engineering and they follow the Unix Philosophies of: Writing simple
> parts connected by clean interfaces… Design programs to be connected
> to other programs…"

> "Top is both an example of this and a chance to further dig into and
> understand the 'Everything is a file' approach to interface design in
> Unix and its derivatives."

> "The high-level functional requirements for `top` are concisely
> described by it's man page — give it a go in your local terminal now:"
>
> ```
> % man top
> NAME
>      top – display sorted information about processes
> DESCRIPTION
>      The top program periodically displays a sorted list of system
>      processes.
>      The default sorting key is pid, but other keys can be used instead.
>      Various output options are available.
> ```

> "### Step Zero — Like all good software engineering we're zero
> indexed! In this step you're going to set your environment up ready
> to begin developing and testing your solution. I'll leave you to setup
> your IDE / editor of choice and programming language of choice. After
> that if you're running on Windows or Mac OS X you'll need either a
> Linux VM, Docker, or WSL so that you can test your version of top."

So the page's own functional core, as verified, is:

1. Step Zero: set up the environment; Linux (or a Linux VM / Docker /
   WSL) is required so `/proc` is available.
2. Periodically display a sorted list of system processes, reading
   process data the Unix "everything is a file" way (i.e. from `/proc`).
3. The default sorting key is pid (per the man-page excerpt the page
   quotes), but other keys can be used instead.
4. Various output options are available.

## Implemented behaviour (this build)

- Language: Python 3, standard library only. No `psutil`, and the
  implementation never shells out to `top`/`ps` — all process data comes
  from `/proc` (see DESIGN.md).
- Summary header, modelled on real `top`:
  - `top - HH:MM:SS up <uptime>, N user(s), load average: a, b, c`
  - `Tasks: T total, R running, S sleeping, P stopped, Z zombie`
  - `%Cpu(s): us, sy, ni, id, wa, hi, si, st`
  - `MiB Mem : total, free, used, buff/cache` and
    `MiB Swap: total, free, used, avail Mem` (avail from `MemAvailable`).
- Process table columns (fixed order, matching real `top`):
  `PID USER PR NI VIRT RES SHR S %CPU %MEM TIME+ COMMAND`
  - `VIRT`/`RES`/`SHR` in KiB (from `/proc/<pid>/stat` `vsize` and
    `/proc/<pid>/statm` resident/shared pages × page size).
  - `S` is the process state letter from `/proc/<pid>/stat`
    (`R`/`S`/`D`/`Z`/`T`/`t`/`X`/`I`).
  - `%MEM` = RES / MemTotal × 100.
  - `TIME+` = (utime + stime) / CLK_TCK, as `M:SS.ss` (or `H:MM:SS`
    once it exceeds an hour).
  - `COMMAND` is the short name from `/proc/<pid>/stat` (`comm`), not
    the full command line.
- Sorting (`-o` / `--sort`): `pid` (default, ascending — following the
  man-page excerpt quoted on the page), `cpu` (descending), `mem`
  (descending), `time` (descending), `virt` (descending), `res`
  (descending), `command` (ascending), `user` (ascending). Unknown sort
  keys are a CLI error (exit 2), not a silent fallback.
- Periodic display: `-d`/`--delay` seconds between refreshes
  (default 3.0, like real `top`); `-n`/`--iterations` limits refreshes.
- Batch / one-shot mode (`-b`/`--batch`): plain-text output to stdout,
  no curses, no screen clearing — this is the mode used for headless
  testing and piping. `-b -n 1` is a single snapshot.
- Filtering: `-u`/`--user` (exact username or numeric UID),
  `-p`/`--pid` (comma-separated PIDs), `--limit N` (max table rows).
- `%CPU` semantics: computed from two samples `delay` seconds apart as
  `(delta utime+stime ticks) / (CLK_TCK × delay) × 100`, i.e. percent of
  one CPU (can exceed 100 on multi-threaded processes, as in real
  `top`). With `-d 0` there is no interval to measure over, so `%CPU`
  is reported as `0.0` rather than fabricated. The header `%Cpu(s)`
  breakdown comes from the delta of `/proc/stat` CPU fields between
  the same two samples (with `-d 0`, from a single sample it is
  reported as all-idle except it still sums to 100 — see DESIGN.md).
- Interactive mode (default when stdout is a TTY and `-b` is not
  given): curses full-screen refresh with keys `q` quit, `P` sort by
  CPU, `M` sort by memory, `N` sort by PID, `T` sort by time.
  Interactive curses behaviour is NOT claimed as headlessly tested
  (see TEST_PLAN.md).
- `--proc-root` is a test/development hook pointing at a fake `/proc`
  tree; it is documented here, not a page feature.

## Deliberate divergences

1. Default sort is `pid`, per the page's quoted man page — real Linux
   `top` defaults to `%CPU`. Use `-o cpu` for the familiar Linux-top
   default.
2. `VIRT`/`RES`/`SHR` are shown in KiB (raw numbers), not with
   `top`'s humanised suffixes, so output stays machine-parseable and
   testable in batch mode.
3. No colour, no field-selection (`f`), no per-CPU display, no tree
   view, no thread view — out of the page's verified core.
4. Header uptime uses `/proc/uptime`; user count is the number of
   distinct UIDs among listed processes (real `top` counts logged-in
   users from utmp — that source is deliberately not read).

## Guarded / NOT built (honest scope limits)

- **Kill / renice and any other privileged action: NOT built.** The
  page body beyond Step Zero was not retrievable (see retrieval caveat),
  so no kill/renice step is claimed as a page requirement here, and no
  such capability is implemented. In interactive mode, pressing `k`
  only shows "kill/renice not supported in this build" — it never
  sends a signal. There is no `--kill` flag.
- **Non-Linux platforms: NOT supported.** Without `/proc` the program
  exits with an error (exit 2) instead of pretending to work. This
  follows the page's Step Zero (Linux VM / Docker / WSL on other OSes).
- **Full `top` parity: NOT claimed.** No config files, no command-line
  editing of a running process's fields, no batch-to-file beyond plain
  stdout redirection, no `htop`-style meters.
- **Steps beyond Step Zero: NOT verified verbatim** for the reason
  above. If a later read of the page shows further numbered steps
  (e.g. specific field or interaction requirements), they must be
  added here and implemented before being claimed.

## CLI summary

```
python3 top.py [-b] [-n N] [-d SECONDS] [-o KEY] [-u USER]
               [-p PID,...] [--limit N] [--proc-root DIR]
```

Exit codes: 0 success, 2 usage / unreadable `/proc` / unknown sort key.
