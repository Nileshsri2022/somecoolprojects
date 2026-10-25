# TEST_PLAN — ccxargs

## Runner

```
python3 -m unittest discover -s tests -v
```

from `~/workspace/somecoolprojects/xargs/`. All tests use harmless
commands only (`echo`, `true`, `cat`, `sed`, `sh -c 'exit N'` for
exit-code tests, `sleep` for the parallelism test). No network, no
destructive commands, no fixture files outside a temporary directory
created per test run. System xargs (`/usr/bin/xargs`, GNU findutils
4.9.0) is used as an oracle in a few comparison tests where noted;
those tests are skipped automatically if system xargs is absent.

## Coverage map

| Area | Tests |
|------|-------|
| Step 1: basic whitespace -> args, `ls \| ccxargs cat` equivalent (via temp files + `cat`) | basic cat over temp files; default utility is echo; utility with 2+ initial args (`sed s/file/test/g` equivalent via echo) |
| Step 2: initial utility arguments preserved on every invocation | echo with prefix args, with `-n 1` (prefix repeated per call) |
| Step 3: `-n` / `--max-args` (incl. `-n2` attached form, `--max-args=2`) | batching 1/2/3 items; `-n 0` is a usage error |
| Step 4: `-P` / `--max-procs` | `-P 2` runs all items (result as a set, order unspecified); `-P 0` accepted; invalid `-P` is a usage error; timing smoke test: `-P 4` with `sleep 0.2` per item finishes materially faster than sequential (bounded, not timing-critical: sequential would take ~0.8 s, parallel must take < 0.7 s — generous margin) |
| `-0` | NUL-separated items, spaces preserved inside items, quotes literal |
| `-I` | replacement in middle/end of args, custom replstr, implies one line per invocation, multi-token line stays one argument, no append when replstr absent |
| `-L` | lines-per-invocation grouping, blank lines skipped and not counted (GNU behaviour, oracle-verified) |
| `-E` | stops at EOF string, rest ignored; ignored in `-0` mode; no default EOF string (`_` passes through) |
| `-r` | empty input runs nothing; without `-r` empty input runs utility once |
| `-t` | command echoed to stderr before running |
| `-p` | prompt printed to stderr; with no controlling terminal the invocation is skipped (documented fallback) |
| `-s` / `-x` | batch split at size limit; single oversized item errors (exit 1); `-x` errors when size forces a short batch |
| `-d` | custom delimiter, quoting disabled |
| Quoting | single quotes, double quotes, backslash escapes, backslash-newline continuation, unmatched quote errors (exit 1) |
| Exit codes | 0; 123 (child exit 42); 124 (child exit 255, and later invocations skipped); 125 (child killed by signal); 127 (utility not found) |
| Oracle comparisons (system xargs, skipped if absent) | basic, `-n`, `-I`, `-L`, `-r`, quoting, `-0` outputs match system xargs on identical inputs |
| Help/version | `--help` exits 0 and mentions usage; `--version` exits 0 |
| Usage errors | unknown option, missing option value, `-n 0`, `-I` without replstr, `-L 0`, `-P` negative, `-s` non-numeric |

## Not tested (deliberately)

- The page's suggested `curl` URL-download test for `-P` (network).
- Exact GNU `-s` byte boundaries (approximate accounting — see SPEC).
- `-p` interactive "yes" path: it needs a controlling terminal, which a
  unit-test harness cannot reliably provide; the no-tty fallback path
  (prompt printed, invocation skipped) is tested instead.
- Parallel output interleaving order (unspecified by design).
