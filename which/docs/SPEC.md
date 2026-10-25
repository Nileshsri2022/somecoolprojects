# SPEC — Build Your Own Which

Source challenge page (read first, 2026-10-25):
https://codingchallenges.fyi/challenges/challenge-which/
Slug used: `challenge-which` — the first-guess slug worked, no
404 correction needed.

## Challenge steps (from the page)

- Step 0: set up the project (Python 3, standard library only).
- Step 1: read the command line, extract the list of commands
  to search for, e.g. `which go ls python3` searches for
  `go`, `ls`, `python3`.
- Step 2: read the `PATH` environment variable to learn where
  to search.
- Step 3: search the PATH directories in order, so the first
  match is the one the shell would run. Basic checks on each
  candidate: it must be a regular file (not a directory) and
  executable.
- Step 4: print the results, one path per line, e.g.
  `which go ls python3` prints `/usr/local/go/bin/go`,
  `/bin/ls`, `/usr/bin/python3` (paths depend on the machine).

The page's man-page excerpt gives the synopsis
`which [-as] program ...`, so the flags below come from that
synopsis plus the behaviour of system `which` (Debian
`/usr/bin/which`), which was probed on this machine to pin
down exit codes and edge cases the page does not spell out.

## Required behaviour

Usage:

```sh
python3 which.py [-as] [--] program ...
python3 which.py -a program ...
python3 which.py -s program ...
```

### Search

- For a bare name (no `/`): split `PATH` on `:` and search
  its directories in order. A candidate is
  `<dir>/<name>`; an empty PATH element means the current
  directory and is printed as `./<name>` (matching system
  `which`).
- For a name containing `/` (relative like `./myprog` or
  absolute like `/bin/ls`): do NOT search PATH; check that
  exact path as given and print it verbatim if it qualifies.
- A candidate qualifies only if it is a regular file
  (symlinks to regular files count) and executable
  (`os.access(path, os.X_OK)`). Directories and
  non-executable files never match.
- Without `-a`, print only the first qualifying match per
  program. With `-a`, print every qualifying match, in PATH
  order, including duplicates when PATH lists the same
  directory twice (system `which` does not de-duplicate).
- All programs are processed in operand order; each match
  is printed on its own line to stdout.

### Flags

- `-a`: print all matches instead of just the first.
- `-s`: silent — print nothing, exit status still reflects
  whether every program was found.
- Flags may be combined (`-as`, `-sa`). Flag parsing stops
  at the first non-flag argument or at `--`; anything after
  that is an operand even if it starts with `-` (so
  `which myprog -a` searches for `myprog` and for `-a`).
- A lone `-` is an operand, not a flag.

### Exit status

- `0`: every program was found (at least one match each).
- `1`: at least one program was not found, or no program
  was given at all. Programs that were found are still
  printed; processing continues past a miss.
- `2`: usage error — an unknown option (e.g. `-x`). Prints
  `Illegal option -x` to stderr and a usage line to stdout,
  and does no searching (matching system `which`).

## Non-goals

- No shell builtins, aliases, or functions: only files on
  disk are found (system `which` on this machine behaves
  the same for the cases tested).
- No `-p`, `--all`, `--read-alias` or other GNU-style long
  options; the page's synopsis is only `[-as]`.
- No tilde expansion or PATH de-duplication.
