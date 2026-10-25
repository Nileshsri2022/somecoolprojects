# SPEC — Build Your Own Xargs (`ccxargs`)

## Resolved challenge page

- Original challenge (read in full, 2026-10-25): **Coding Challenge #50 — xargs**
  <https://codingchallenges.substack.com/p/coding-challenge-50-xargs>
  (published 2024-02-24; author John Crickett).
- The challenge is also listed on codingchallenges.fyi under the `unix` and
  `intermediate` tag pages (verified: "Build Your Own Xargs — build your own
  version of the Unix command line tool xargs!"). The fyi mirror page itself
  was NOT opened: the attempt to follow the tag-page link to it hit a
  rate limit (HTTP 429) and was not retried. The Substack page above is the
  canonical, fully-read source for the steps below, so no spec content is
  guessed. Tags per the task brief: intermediate, systems, cli.

## Challenge steps (as written on the page) and implementation status

| # | Step on the page | Status |
|---|------------------|--------|
| 0 | Set up the environment / IDE / language of choice | Done — Python 3 stdlib only, `ccxargs.py` |
| 1 | `ccxargs` takes a whitespace-separated set of strings from stdin and converts them into command-line arguments for a utility. Test: create `test-1/2/3.txt`, then `ls \| ccxargs cat` prints all three files' contents (equivalent to `cat test-1.txt test-2.txt test-3.txt`) | Done |
| 2 | Support additional command-line arguments to the utility. Test: `ls \| ccxargs sed s/file/test/g` rewrites "file" → "test"; test with 2+ arguments to the command too | Done — any number of initial utility arguments are passed before the stdin arguments on every invocation |
| 3 | Support `-n` (`--max-args`): maximum stdin arguments per invocation (default 5000 in the man excerpt). Test: `ls \| ccxargs -n 1 cat` invokes `cat` three times, once per file | Done |
| 4 | Support `-P` (`--max-procs`): run at most that many invocations at once; `0` = as many as possible. Test suggested: `cat urls.txt \| ccxargs -n 1 -P 1 curl` vs `-P 10 curl`, timing the difference | Done (parallel execution; the curl/URL test itself is NOT run — it needs network access and would download arbitrary pages. Parallelism is instead tested with harmless `echo`/`true` and a sleep-based ordering check) |
| — | "You can take this challenge further by adding support for the other options detailed on the man page" | Done, in part — see "Extra options" below. Bonus point "use your own version of cat" is NOT claimed: the page's `cat` test is run with the system `cat`, not a local cat build |

## Command line

```
ccxargs [options] [utility [initial-argument ...]]
```

Default utility is `echo` (as in GNU xargs). Options may use the
`--opt=value` or `--opt value` form, and short options may be bundled
where they take no argument (e.g. `-rt`); `-n`, `-I`, `-L`, `-E`, `-P`,
`-s`, `-d` take a value either attached (`-n2`) or as the next argument.

## Extra options (beyond the four numbered steps)

All are implemented and tested:

- `-0, --null` — items are NUL-separated; no quoting, no EOF string.
- `-I replstr, --replace=replstr` — replace-string mode: one input *line*
  per invocation (implies `-L 1`); every occurrence of `replstr` in the
  initial utility arguments is replaced by the line. If no initial argument
  contains `replstr`, the line is NOT appended (matches GNU xargs, verified
  against system xargs 4.9.0). A custom replstr other than `{}` is allowed.
- `-L max-lines, --max-lines=max-lines` — at most that many input lines
  per invocation (all tokens of those lines are passed).
- `-E eofstr, --eof=eofstr` — stop reading at an item exactly equal to
  `eofstr`; the rest of stdin is ignored. Ignored in `-0` mode (as in GNU).
  There is NO default EOF string: a bare `_` item is passed through, matching
  GNU xargs (verified against system xargs).
- `-p, --interactive` — print each command to stderr as `cmd args ?...`
  and run it only on a `y`/`yes` answer read from `/dev/tty`.
- `-t, --verbose` — print each command to stderr before running it.
- `-r, --no-run-if-empty` — do not run the utility at all when stdin
  yields no items (without `-r`, the utility runs once with no stdin args,
  matching GNU).
- `-x` — exit with an error instead of running a batch when the `-s`
  size limit would force a batch smaller than the requested `-n` count,
  or when a single item alone exceeds `-s`.
- `-s size, --max-chars=size` — cap on the approximate byte size of one
  invocation's argument list (item bytes plus one separator per item).
  This is an approximation: GNU counts the utility name, environment and
  other overhead, so exact GNU `-s` boundaries are NOT reproduced
  (see "Divergences").
- `-d delim, --delimiter=delim` — GNU-style input delimiter (a single
  character, or a C-style escape such as `\n` or `\t`); quoting is disabled
  in this mode. This is a bonus, not required by the page.
- `--help`, `--version`.

## Input parsing (GNU-compatible core)

- Whitespace mode (default): items are separated by spaces, tabs and
  newlines. Single quotes protect everything until the next single quote;
  double quotes protect everything except backslash escapes before
  `$`, `` ` ``, `"`, `\` and newline; an unquoted backslash escapes the
  next character (a backslash-newline is a line continuation). An
  unmatched quote is an error (exit 1, message on stderr) — GNU also
  errors on unmatched quotes.
- `-0` mode: items are split on NUL bytes only; quotes and backslashes
  are literal.
- `-d` mode: items are split on the delimiter only; quotes/backslashes
  are literal; a trailing delimiter does not create an empty item.

## Exit codes (matching GNU xargs, verified against system xargs 4.9.0)

- `0` — all invocations succeeded.
- `1` — usage error, unmatched quote, or an `-s`/`-x` size violation.
- `123` — some invocation exited with a status in 1–125.
- `124` — some invocation exited with status 255 (remaining sequential
  invocations are then skipped, as in GNU).
- `125` — some invocation was killed by a signal.
- `127` — the utility could not be started (not found / not executable).
- A utility exit status of 255 aborts further invocations in sequential
  mode; in parallel mode no *new* invocations are started after one is
  observed, but already-running ones finish.

## Deliberate divergences from GNU xargs / the man page

1. `-s` accounting is approximate (item bytes + separators only; GNU
   also counts the utility name and environment). Small `-s` values
   therefore behave differently from GNU at the boundary.
2. `-P 0` ("as many as possible") is implemented as one worker per batch
   rather than a truly unbounded process pool.
3. `-p` reads the answer from `/dev/tty`. If there is no controlling
   terminal, the prompt is still printed to stderr but the invocation is
   skipped (treated as "no") instead of blocking or failing. GNU under
   the same conditions would also fail to read a tty; the skip-and-
   continue behaviour is the documented safe fallback here.
4. Parallel (`-P`) output ordering is unspecified (as in GNU): outputs
   of concurrent invocations may interleave. Tests therefore check
   parallel results as a set, not in order.
5. `-S` (max replace size), `-J`, `-R` (BSD-only options from the man
   excerpt) and `-a` (read from a file instead of stdin) are NOT
   implemented; passing them is a usage error. See "Not built".
6. Long-option `--max-lines`/`--max-args` etc. follow GNU names; the
   BSD-only long forms are not provided.
7. The utility's stdin is inherited from `ccxargs`'s stdin only when
   there is nothing else to read — in practice, since `ccxargs` consumes
   stdin to build arguments, child processes get `/dev/null` as stdin
   (except that `-p` still uses `/dev/tty`). This matches GNU xargs
   behaviour of redirecting the utility's stdin from `/dev/null`.

## Not built

- `-S`, `-J`, `-R`, `-a` options (see above).
- The page's suggested `curl` download test for `-P` (network use;
  replaced by harmless local tests — see TEST_PLAN.md).
- No shell interpretation: utility arguments are passed via `exec`
  directly, never through a shell, so shell metacharacters in items are
  data, not code. This is a safety property, not a missing feature:
  `ccxargs` never runs `sh -c` on constructed commands.
- No reading of items from a file (`-a`); stdin only.

## Safety

- Subprocess invocation uses `subprocess.run` with an argument list
  (no shell). Test commands are limited to `echo`, `true`, `cat`, `sed`,
  `sh -c 'exit N'` (for exit-code tests only) and `sleep` — never
  destructive commands.
