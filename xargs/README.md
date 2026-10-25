# Build Your Own Xargs — `ccxargs`

A small, Python-3-stdlib-only reimplementation of the Unix `xargs`
command, built for Coding Challenge #50.

Challenge page (read in full):
<https://codingchallenges.substack.com/p/coding-challenge-50-xargs>
— also listed on codingchallenges.fyi under the `unix` and `intermediate`
tags. Tags: intermediate, systems, cli.

## Run

```sh
python3 ccxargs.py [options] [utility [initial-argument ...]]
# default utility is echo
ls | python3 ccxargs.py cat
ls | python3 ccxargs.py sed s/file/test/g
ls | python3 ccxargs.py -n 1 cat
cat urls.txt | python3 ccxargs.py -n 1 -P 10 curl   # page's -P example
```

## Supported options

`-n/--max-args`, `-P/--max-procs`, `-0/--null`, `-I/--replace`
(implies one line per invocation), `-L/--max-lines` (non-blank lines),
`-E/--eof`, `-p/--interactive`, `-t/--verbose`, `-r/--no-run-if-empty`,
`-s/--max-chars` (approximate), `-x`, `-d/--delimiter`, `--help`,
`--version`.

Input parsing follows GNU quoting rules (single/double quotes, backslash
escapes); arguments are passed to the utility via `exec`, never through
a shell. Exit codes follow GNU xargs: 0 ok, 123 child exit 1–125,
124 child exit 255, 125 child killed by signal, 127 utility not found,
1 usage/size errors.

## Docs

- `docs/SPEC.md` — challenge steps, supported features, divergences,
  and everything NOT built, honestly stated.
- `docs/DESIGN.md` — tokeniser, batcher, runner design.
- `docs/TEST_PLAN.md` — test coverage map.

## Tests

```sh
python3 -m unittest discover -s tests -v
# 73 tests, all passing (includes comparisons against system xargs
# as oracle, skipped automatically if system xargs is absent)
```

## Not built

`-S`, `-J`, `-R`, `-a` options; the page's live `curl` download test
for `-P` (network use — replaced by harmless local parallelism tests);
exact GNU `-s` byte accounting (approximate here). See `docs/SPEC.md`.
