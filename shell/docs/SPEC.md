# SPEC — Build Your Own Shell (Coding Challenges #14)

Source: https://codingchallenges.fyi/challenges/challenge-shell/
(read 2026-10-25; that URL loads, no slug correction needed).
The project is named `ccsh` on the challenge page, for
**C**oding **C**hallenges **Sh**ell.

## Behaviour, step by step

### Step 1 — Single command, prompt `ccsh>`
Start, print the prompt `ccsh> `, read one line, trim trailing
whitespace/newlines, spawn a process to run it, print its output
below the prompt. (The page's step-1 shell exits after one command;
step 2 supersedes this with a loop.)

### Step 2 — Loop until `exit`
Wrap command handling in a loop that runs indefinitely until the
user enters the builtin `exit`. Wait for the running command to
finish before reading the next command. End of input (EOF / Ctrl-D
on a terminal) also ends the shell.

### Step 3 — Unknown commands must not crash the shell
Running a command that does not exist prints an error and returns
to the prompt. The page's (Rust) example prints:

```
ccsh> fubar
No such file or directory (os error 2)
ccsh> exit
```

### Step 4 — External commands with arguments
Split the input into a command and its arguments (e.g. `ls -la`,
`cat <filename>`) and pass them to the spawned process. Quoted
arguments stay together (e.g. `echo "hello world"` prints one
argument, `hello world`).

### Step 5 — Builtins `cd` and `pwd`
`cd` must be a builtin because it changes the shell's own state
(its working directory); a child process could not change its
parent's directory. `pwd` prints the shell's current working
directory. Examples from the page: `cd target`, then `ls` lists
that directory; `cd ..` returns to the parent; `pwd` reflects both
moves. `cd` with no argument goes to the user's home directory
(standard shell behaviour; the page does not spell this out).

### Step 6 — Pipes
`|` chains commands: the stdout of one command becomes the stdin
of the next, e.g. `cat test.txt | wc -l` prints the line count.
Multi-stage pipelines (`a | b | c`) work, and a `|` inside quotes
is data, not a pipe. Stages wait for each other; the shell waits
for the whole pipeline before prompting again.

### Step 7 — Ctrl-C (SIGINT)
Ctrl-C must not terminate the shell, but must still terminate a
running child command. So the shell ignores SIGINT in itself and
restores the default SIGINT disposition in children.

### Step 8 — History
1. Save all executed commands to the history.
2. Save the history to disk when the shell exits, to
   `.ccsh_history` in the user's HOME directory.
3. Reload the history from disk when the shell starts.
4. Allow scrolling through history with the up/down arrow keys.
5. Support the builtin `history`, which lists the history, one
   command per line, e.g.:

```
ccsh> history
ls
pwd
ls
```

Note the page's example: the `history` command itself does not
appear in its own listing.

## Out of scope (page does not ask for these)
- Input/output redirection (`>`, `<`, `>>`): not in steps 1–8.
  A `>` typed on a command line is passed to the command as an
  ordinary argument (so `echo hi > out` prints `hi > out`).
- Shell scripts, variables, globbing, job control, `export` /
  `unset` (mentioned only as examples of other shells' builtins),
  command substitution, background `&`.
- `cd -` (previous directory): not specified; `cd -` fails as an
  unknown directory, like any other bad `cd` target.

## Interface
- Run: `python3 shell.py` (no arguments). Any command-line
  argument is a usage error (exit code 2).
- Prompt: `ccsh> `, written to stdout.
- History file: `$HOME/.ccsh_history` by default. The environment
  variable `CCSH_HISTORY_FILE`, when set, overrides the path;
  this exists only so tests can use a scratch file instead of
  touching the real home directory, and is documented in README.md.
- Exit code: 0 on `exit` / EOF; the exit code given to
  `exit N` (integer N) if used; 2 on a usage error.
