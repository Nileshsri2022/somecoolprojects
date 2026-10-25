# shell — Build Your Own Shell

Coding Challenges #14, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A minimal shell with the prompt `ccsh> `: it runs external
commands with arguments (via `subprocess`), builtins `cd`,
`pwd`, `history`, and `exit`, multi-stage pipes, SIGINT
handling (Ctrl-C kills the child, not the shell), and a
history saved to `~/.ccsh_history` on exit and reloaded
on start, with up/down arrow scrolling on a terminal
(via stdlib `readline`).

## Usage

```sh
python3 shell.py
ccsh> ls
ccsh> cat file.txt | wc -l
ccsh> cd subdir
ccsh> pwd
ccsh> history
ccsh> exit
```

No arguments. `CCSH_HISTORY_FILE`, when set, overrides the
history file path (used by the tests so they never touch
the real `~/.ccsh_history`).

Not implemented, deliberately — the challenge page does not
ask for them: redirection (`>`, `<`), globbing, variables,
shell scripts, job control, `cd -`. See `docs/SPEC.md`.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests drive the shell non-interactively through stdin/stdout
pipes (plus one direct SIGINT test) and cover the prompt loop,
external commands and arguments, `cd`/`pwd`, pipes (including
a quoted pipe), unknown commands, history listing and
persistence, empty lines, EOF, and SIGINT survival.

## Files

- `shell.py` — the shell.
- `docs/SPEC.md` — challenge spec, step by step.
- `docs/DESIGN.md` — assumptions and structure.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_shell.py` — the test suite.
