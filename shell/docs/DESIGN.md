# DESIGN — shell (`shell.py`)

Python 3 standard library only, single file. External programs are
run with `subprocess`, never reimplemented.

## Assumptions (stated before coding)

1. Prompt is the literal string `ccsh> ` (page: `ccsh>`, examples
   show a space before the typed command). It is written to stdout,
   not stderr, so piped test harnesses see the same transcript a
   terminal user sees.
2. Input lines are split with `shlex.split` (POSIX mode): quoting
   and backslash escapes behave like a normal shell for arguments,
   and a `shlex` error (e.g. an unterminated quote) is a shell
   error, not a crash.
3. The prompt loop trims the whole line (leading and trailing
   whitespace). Empty lines are ignored: no error, not recorded
   in history, prompt again.
4. History rule: every successfully parsed non-empty line is
   recorded, except a line whose command is the `history` builtin
   itself (a line rejected as a syntax error is not recorded). This is what
   makes the page's step-8 example come out exactly (the listing
   shows `ls, pwd, ls`, not a trailing `history`). `exit` is
   recorded like any other command; it is simply never listed
   afterwards in that session, and it is saved to disk on exit
   like the rest.
5. History file format is one command per line, exactly as the
   `history` builtin prints it, so the file and the listing agree.
   On exit the whole history (loaded + new) is written back,
   replacing the file. A missing file at startup is normal (first
   run); an unreadable/unwritable file prints a warning to stderr
   and the shell carries on in-memory — history must never kill
   the shell.
6. Arrow-key scrolling needs a terminal and the stdlib `readline`
   module. It is therefore enabled only when stdin is a TTY and
   `readline` imports; the loaded history is fed to `readline`
   and input is read with `input(prompt)`. When stdin is a pipe
   (tests, scripts), plain `sys.stdin.readline()` is used and
   there is nothing to scroll — no behaviour difference otherwise.
7. Signals: the shell sets SIGINT to `SIG_IGN` before the loop.
   `subprocess.Popen` restores default signal dispositions in the
   child by default (`restore_signals=True`), so a child still
   dies on Ctrl-C while the parent survives. `KeyboardInterrupt`
   is also caught around input as a belt-and-braces measure (it
   can still surface on some platforms) and just re-prompts.
8. Unknown-command error text: Python's `FileNotFoundError` for a
   missing program is reported as
   `No such file or directory (os error 2)` on its own line,
   matching the page's Rust example verbatim (the program name is
   not prepended, to match the page). Other spawn failures
   (e.g. permission denied) print the OS error string instead.
   Errors go to stderr; the shell then re-prompts.
9. `cd` errors print `cd: <dir>: No such file or directory` (or
   the OS error string) to stderr and do not change directory.
   `cd` with no argument goes to `$HOME`; if `$HOME` is unset,
   that is an error. `cd` with more than one argument is an error
   (`cd: too many arguments`) and changes nothing.
10. `pwd` prints `os.getcwd()`. It is a builtin for the
    single-command case, so it always reflects the shell's own
    `os.chdir` state.
11. `exit` with no argument exits 0. `exit N` (integer) exits
    with N. `exit` with a non-integer argument prints an error
    and does not exit. (The page only specifies bare `exit`;
    the numeric form is the standard shell extension and is
    kept to this one obvious case.)
12. Pipelines: the line is split on unquoted `|` characters by a
    small scanner that tracks single quotes, double quotes, and
    backslash escapes, so `echo "a|b"` stays one command. Each
    segment is then `shlex.split`. Stages are chained with
    `subprocess.Popen(stdout=PIPE)` and the parent closes each
    intermediate stdout after handing it to the next stage, so a
    stage that exits early gives the previous stage SIGPIPE
    instead of hanging. The shell waits for every stage.
    Deliberate limitation: builtins are not run inside a pipeline
    (a pipeline stage cannot change the shell's own directory,
    and `history`/`exit` mid-pipeline have no sensible meaning),
    except `pwd`, which is run as the external `pwd` program —
    it inherits the shell's working directory, so its output is
    identical. A builtin other than `pwd` in a pipeline prints
    `ccsh: <name>: builtin not supported in a pipeline` and the
    pipeline does not run. An empty pipeline segment
    (`ls |`, `| wc`) is a syntax error and does not run.
13. No redirection, globbing, variables, or scripts (see SPEC.md).
    This is the page's step list, not a POSIX shell.

## Structure (`shell.py`)

- `history_file_path()` — `CCSH_HISTORY_FILE` override, else
  `$HOME/.ccsh_history`.
- `load_history(path)` / `save_history(path, history)` — plain
  lines, tolerant of a missing/unreadable file.
- `split_pipeline(line)` — quote-aware split on `|`.
- `parse_command(segment)` — `shlex.split` wrapper.
- `run_builtin(argv, history)` — `cd`, `pwd`, `history`, `exit`.
  Returns `(should_exit, exit_code)` or `None` if not a builtin.
  Builtins print to stdout (`pwd`, `history`) or stderr (errors).
- `run_pipeline(segments)` — Popen chain for external commands,
  with the `pwd`-as-external rule and the builtin rejection above.
- `run_line(line, history)` — record history (rule 4), dispatch:
  single segment → builtin or external; multi-segment → pipeline.
  Returns `(should_exit, exit_code)`.
- `main()` — argument check, SIGINT ignore, history load,
  prompt loop (readline path on a TTY, plain-readline path
  otherwise), history save on every exit path (builtin `exit`,
  EOF, Ctrl-D). Returns the exit code; `sys.exit(main())` only
  under `if __name__ == "__main__"`, so tests can import helpers.

## Verification
`python3 -m unittest discover -s tests -v` — see TEST_PLAN.md.
