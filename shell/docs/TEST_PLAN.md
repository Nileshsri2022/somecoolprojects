# TEST_PLAN — shell

Harness: `tests/test_shell.py` (unittest). The shell is driven
non-interactively: `subprocess.run([sys.executable, shell.py],
input=..., capture_output=True, text=True, cwd=<tmpdir>)` with
`CCSH_HISTORY_FILE` pointed at a scratch file in the temp dir, so
no test touches the real `$HOME/.ccsh_history`. No interactive
terminal is needed; the one signal test uses `Popen` + `SIGINT`
directly. All tests use only programs present on a normal Linux
system (`echo`, `cat`, `wc`, `grep`, `ls`).

## Cases

1. Prompt + single command: `echo hello` then `exit` → output
   contains the `ccsh> ` prompt and `hello`.
2. Loop: two `echo` commands then `exit` → both outputs appear,
   prompt appears at least 3 times.
3. `exit` terminates: commands after `exit` in the input are
   never run; exit code 0.
4. EOF terminates: input ends without `exit` → shell exits
   cleanly (code 0), prior output present.
5. Unknown command: a nonsense command prints
   `No such file or directory` and the shell continues to the
   next command and exits normally.
6. Arguments: `echo a b c` prints `a b c`; `cat <file>` prints
   the file's contents (external program, not reimplemented).
7. Quoted arguments: `echo "hello world"` prints `hello world`;
   `echo 'a|b'` / quoted-pipe case in the pipeline tests.
8. `cd` / `pwd`: `pwd`, `cd <subdir>`, `pwd`, `cd ..`, `pwd` →
   the middle `pwd` is the subdir, the last is the start dir.
9. `cd` with no argument → `$HOME` (test sets `HOME` to a temp dir).
10. `cd` to a nonexistent directory → error mentioning
    `No such file or directory`, shell continues, directory
    unchanged (next `pwd` is the start dir).
11. `ls` in a temp dir lists a file created there (external
    command proof, independent of `echo`).
12. Pipeline, two stages: `cat <file> | wc -l` → the line count.
13. Pipeline, three stages: `cat <file> | grep <pat> | wc -l` →
    the matching-line count.
14. Pipeline, word count: `echo a b c | wc -w` → `3`.
15. Quoted pipe is not a pipe: `echo "a|b" | cat` → output
    contains `a|b` (single line, not split into two commands).
16. Empty pipeline segment: `ls |` → a syntax-error message,
    shell continues, exit code 0 overall.
17. History builtin: `echo one`, `echo two`, `history` → the
    listing contains `echo one` and `echo two` as consecutive
    lines, and no line that is exactly `history`.
18. History persistence: session 1 runs commands and exits;
    the history file contains them; session 2 with the same
    history file runs `history` → the previous session's
    commands are listed. Also checks the file is created.
19. History reload on start is covered by case 18 (session 2).
20. SIGINT: start the shell via `Popen`, send `SIGINT`, assert
    the process is still alive, then feed `echo alive` + `exit`
    → `alive` appears and the shell exits. (The shell ignores
    SIGINT; children restore the default — child SIGINT
    behaviour is design, not separately unit-tested here
    because it needs a TTY Ctrl-C; see note below.)
21. Empty lines: blank lines before/between commands are
    ignored, shell still runs the commands and exits.

## Not tested (and why)
- Arrow-key scrolling: needs a real TTY + terminal emulator;
  the code path is the stdlib `readline` integration enabled
  only on a TTY (DESIGN.md rule 6). It cannot be exercised
  meaningfully through pipes, so it is verified by code
  inspection, not a unit test.
- Ctrl-C killing a child: same TTY reason as above. The
  mechanism (parent `SIG_IGN` + child `restore_signals`)
  is the standard `subprocess` behaviour and is stated in
  DESIGN.md rule 7.
- Redirection / globbing / variables: out of scope (SPEC.md).

## Run
```sh
python3 -m unittest discover -s tests -v
```
run from `shell/`. All tests must pass; any failure is a bug
in the shell, not in the test, unless the failure names a
missing system program (`echo`, `cat`, `wc`, `grep`, `ls`).
