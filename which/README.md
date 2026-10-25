# which — Build Your Own Which

Coding Challenges #60, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Searches `PATH` for executable programs, like Unix `which`.
Python 3 standard library only, single file `which.py`.

## Usage

```sh
python3 which.py [-as] [--] program ...
python3 which.py ls python3
python3 which.py -a ls
python3 which.py -s ls; echo $?   # silent: exit status only
python3 which.py ./myprog /bin/ls
python3 which.py -- -a            # program literally named -a
```

- Bare names are searched in PATH order; the first match
  wins unless `-a` prints every match.
- Names containing `/` are checked as given (PATH is not
  searched) and printed verbatim when they qualify.
- A match must be a regular file and executable;
  directories and non-executable files never match.
- Exit status: `0` every program found, `1` any program
  not found (or no programs given), `2` unknown option.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use temporary directories with a controlled PATH,
never the real PATH alone, plus spot-checks against system
`/usr/bin/which` under the same controlled PATH.

## Deliberate divergences

- Usage message: on an unknown option this tool prints
  `Usage: <argv[0]> [-as] args` to stdout and
  `Illegal option -x` to stderr, exit 2 — the same split
  and wording as system `which`, except the program name
  is whatever `argv[0]` was (`which.py` when run as
  `python3 which.py`, `/usr/bin/which` for the system tool).
- Only `-a` and `-s` are implemented, per the page's
  synopsis `which [-as]`. No GNU long options.
- The challenge page never states exit codes; the 0/1/2
  scheme above was taken from probed system `which`
  behaviour and is documented in `docs/SPEC.md`.
