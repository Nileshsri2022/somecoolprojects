# DESIGN — which

## Assumptions (stated before coding)

1. Python 3, standard library only, single file `which.py`
   (ponytail: minimum code for the page's steps + the
   `[-as]` synopsis; nothing speculative).
2. `PATH` splitting is `os.pathsep` (`:` on Unix). An unset
   `PATH` means "search nowhere" (system `which` with `PATH`
   unset finds nothing); an empty string element means `.`
   (verified: `PATH=:<dir>` with cwd `<dir>` printed
   `./myprog`).
3. "Executable" = `os.path.isfile()` and
   `os.access(..., os.X_OK)`. `isfile` follows symlinks, so
   a symlink to an executable file qualifies and a symlink
   to a directory or a dangling symlink does not. This is
   the page's "regular file and executable" check, nothing
   more (no mode-bit inspection: `os.access` reflects the
   real user, which is what the shell would do).
4. Output paths are built with `os.path.join(dir, name)`,
   so a `.` element naturally yields `./name`, and a
   trailing-slash directory does not produce a double slash.
   Slash-containing operands are printed exactly as typed.
5. Exit codes follow probed system `which` behaviour
   (0 all found / 1 any missing or no operands / 2 bad
   option), because the page itself never states them.
6. Flag parsing is BSD-style and stops at the first
   operand, matching probed system `which`
   (`which myprog -a` treats `-a` as a second program).

## Structure

`which.py` — three small pieces, no classes needed:

- `parse_args(argv)` -> `(all_matches, silent, programs)`
  or raises `UsageError(option_char)`. Walks argv while an
  argument starts with `-`, is longer than `-`, and is not
  `--`; each character after `-` must be `a` or `s`.
  `--` ends flag parsing; the rest are programs.
- `find_matches(name, path_dirs, all_matches)` -> list of
  paths. Slash names: single-candidate check. Bare names:
  iterate `path_dirs` in order, keep every qualifying
  candidate (or stop at the first unless `all_matches`).
- `main(argv, environ)` -> int. Builds `path_dirs` from
  `environ.get("PATH")` (unset -> `[]`; otherwise split on
  `:`), prints matches unless silent, returns 0/1/2.
  `main` takes `environ` as a parameter so tests can inject
  a controlled PATH without touching the real environment.

`PATH` is read once, at startup, not per program.

## Verified against system `which`

Probed on this machine (Debian `/usr/bin/which`) before
coding; see SPEC.md and `docs/TEST_PLAN.md`:

- `which ls nonexistent` prints the found path, exit 1.
- `which -a ls` prints both `/usr/bin/ls` and `/bin/ls`
  (distinct path strings even though `/bin` -> `usr/bin`).
- `which -a <dir>:<dir>` prints the same path twice.
- `which -x ls` prints usage to stdout, `Illegal option -x`
  to stderr, exit 2.
- `which` with no operands: no output, exit 1.
- Non-executable files and directories named like the
  program never match; `./myprog` and `/abs/myprog` print
  verbatim when executable.
