# DESIGN — ccxargs

## Overview

One file, Python 3 standard library only: `ccxargs.py`. Pipeline:

```
stdin (bytes) -> tokeniser -> items (with line numbers)
             -> batcher (applies -n / -L / -I / -s / -x / -E / -r)
             -> command builder (initial args + items, or -I replacement)
             -> runner (sequential, or ThreadPoolExecutor for -P)
             -> exit-code aggregation (GNU rules)
```

Everything is driven from parsed bytes decoded as UTF-8 with
`surrogateescape`, so non-UTF-8 filenames survive round-tripping to the
child's argv (re-encoded with the same error handler).

## Tokeniser

`tokenise(data, mode)` returns a list of `Item(text, line)` where `line`
is the 0-based input line the item started on (needed for `-L`/`-I`).

- Whitespace mode implements the GNU quoting rules described in SPEC.md,
  scanning byte-by-byte over the decoded string: blank separators are
  space/tab/newline (and CR is treated as a normal character, matching
  GNU? — note: GNU treats `\r` as a regular character too, so it is kept
  inside items). A backslash-newline outside quotes is a line
  continuation (consumed, and the line counter advances). Unmatched
  quotes raise `XargsError` (exit 1).
- `-0` mode splits on `\x00`; a trailing NUL does not produce an empty
  trailing item, but interior empty items (consecutive NULs) are kept.
  In `-0` and `-d` modes each item is assigned its own line number, so
  `-L`/`-I` treat one item as one line there.
- `-d` mode splits on the single delimiter character; quoting disabled.
  A trailing delimiter does not produce an empty trailing item.

The EOF string (`-E`) is applied after tokenising: items are cut at the
first item exactly equal to the EOF string. (In `-0` mode it is ignored.)

## Batcher

Batching walks the item list in order and cuts a batch when any limit
would be exceeded:

- `-n N`: at most N items per batch (`-I` forces N effectively 1 line,
  handled before `-n` — see below).
- `-L M`: at most M *non-blank* input lines per batch (GNU counts only
  non-blank lines for `-L`, verified against system xargs: blank lines
  neither produce an invocation nor consume line budget). Items carry
  their starting line; the batcher groups items by line, drops blank
  lines, then groups consecutive non-blank lines.
- `-I replstr`: input is grouped by line first; each non-empty line
  becomes exactly one invocation, regardless of `-n`. Empty lines are
  skipped (GNU `-I` skips empty lines). Replacement is a plain string
  replacement of every occurrence of `replstr` in every initial argument.
- `-s S`: a batch's size is `sum(len(item) + 1)`. Adding an item that
  would exceed S flushes the current batch first. A single item larger
  than S is an error (exit 1, "argument line too long"), matching the
  GNU observation for tiny `-s` values. With `-x`, flushing early
  because of `-s` while the `-n` count was not reached is also an error.
- `-r`: if the item list is empty (after EOF cut), produce no batches.
  Without `-r`, produce exactly one empty batch so the utility runs once.

Per-line grouping for `-L`/`-I` is built from items' line numbers;
blank lines (no items) are dropped from grouping entirely.

## Command builder

- Normal mode: `command = [utility] + initial_args + batch_items`.
- `-I` mode: `command = [utility] + [arg.replace(replstr, line) for arg
  in initial_args]` where `line` is the raw line text (the items of that
  line joined by a single space — for `-I`, GNU passes the whole line
  with its original spacing collapsed? GNU `-I` replaces with the line
  as read, with leading blanks stripped and internal spacing preserved
  as typed except that the line is a single argument. We preserve the
  line's text as tokenised: items of the line joined by one space, which
  for ordinary single-token lines is exact, and for multi-token lines
  matches the "a b" behaviour verified against system xargs).
  If `initial_args` is empty, the line itself is the argument
  (`[utility, line]`).

Wait — one correction to the above: for `-I`, the replacement text is
the line with its tokens joined by a single space, and the whole line
becomes ONE argument even if it contains spaces (verified: `xargs -I{}
echo pre-{}-post` on input `a b` printed `pre-a b-post`, i.e. one
argument containing a space).

## Runner

- Sequential (`-P` unset or 1): `subprocess.run(cmd, stdin=DEVNULL)`,
  stdout/stderr inherited so output goes straight to the terminal, as
  in real xargs. Exit status mapped per SPEC.md; status 255 stops the
  loop.
- Parallel (`-P > 1` or 0): a `ThreadPoolExecutor` runs invocations
  concurrently (threads only run subprocesses, so the GIL is not a
  bottleneck). Results are collected as they complete; the aggregate
  exit code follows the same rules, with 255 treated as "stop starting
  new work" (already-submitted work still completes).
- `-t`: the command line (arguments joined by a single space, no
  quoting — matching GNU's trace format) is written to stderr before
  each invocation.
- `-p`: the same trace line plus ` ?... ` is written to stderr, then
  one line is read from `/dev/tty` if it can be opened; an answer
  starting with `y`/`Y` runs the command, anything else skips it.
  If `/dev/tty` cannot be opened, the invocation is skipped.
- Missing utility: `FileNotFoundError`/`PermissionError` from
  `subprocess.run` maps to exit 127 with `ccxargs: <utility>: No such
  file or directory` on stderr, and no further invocations are attempted.
- Signal death: a negative return code maps to exit 125.

## Error handling

All user-facing errors go through `XargsError` (message prefixed
`ccxargs: `, exit 1) except the GNU exit-code rules above. Usage errors
print a short usage hint to stderr. `--help` prints usage to stdout and
exits 0.

## Why no shell

Constructed commands are never passed to a shell, so an item such as
`$(rm -rf ~)` or `; rm ...` is passed as a single literal argument to
the utility. This is both the GNU behaviour and the safe one.
