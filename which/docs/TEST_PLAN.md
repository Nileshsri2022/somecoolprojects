# TEST_PLAN — which

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

## Rules

- Tests NEVER rely on the real PATH alone: every search
  test builds temporary directories with `tempfile`,
  creates fixture files with controlled modes (executable
  `0o755`, non-executable `0o644`), and passes an explicit
  controlled PATH via `main(argv, environ)` or a subprocess
  environment. Tests that do compare against system `which`
  invoke `/usr/bin/which` with the same controlled PATH.
- Tests call `main()` in-process (capturing stdout/stderr
  via `contextlib.redirect_stdout/redirect_stderr`) for
  exit codes and output, plus a few subprocess runs of
  `python3 which.py` to verify the real entry point.

## Cases

1. Bare name found in PATH -> first directory's path,
   exit 0.
2. Same name in two PATH dirs -> without `-a`, first only;
   with `-a`, both in PATH order.
3. Same directory listed twice in PATH, with `-a` -> path
   printed twice (no de-duplication, as system `which`).
4. Non-executable file skipped; search continues to a
   later directory that has an executable copy.
5. Directory with the program's name skipped (not a file).
6. Name not found anywhere -> no output, exit 1.
7. Mixed found + not found -> found paths printed, exit 1.
8. Multiple programs -> results in operand order, exit 0
   only if all found.
9. Absolute path operand, executable -> printed verbatim,
   exit 0; non-executable or missing -> exit 1.
10. Relative slash operand `./myprog` (cwd = fixture dir)
    -> printed verbatim, exit 0; `./plain` (non-executable)
    and `./adir` (directory) -> exit 1.
11. Empty PATH element -> current directory, printed as
    `./name`.
12. PATH unset -> nothing found, exit 1.
13. `-s` suppresses all output, exit code unchanged
    (0 found / 1 missing); `-as` combined works.
14. `--` ends flag parsing: `which -- -a` searches for a
    program literally named `-a`.
15. Flag after first operand is an operand:
    `which myprog -a` finds `myprog`, misses `-a`, exit 1.
16. Unknown option `-x` (and `-ax`) -> usage line on
    stdout, `Illegal option -x` on stderr, exit 2, no search.
17. No operands (with or without `-a`) -> no output,
    exit 1.
18. Lone `-` and empty-string operand -> not found, exit 1.
19. Symlink to an executable file qualifies; dangling
    symlink and symlink to a directory do not.
20. Comparison spot-checks vs system `/usr/bin/which` under
    the same controlled PATH (first match, `-a`, missing,
    mixed) — outputs and exit codes agree, except the
    documented usage-line program-name difference (see
    README.md divergences).

## Success criteria

All tests pass (`OK`), no test touches the real PATH
except the comparison spot-checks which override PATH
explicitly, and `__pycache__` is removed after the run.
