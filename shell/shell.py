#!/usr/bin/env python3
"""ccsh: a minimal shell (Coding Challenges #14).

Steps 1-8 of https://codingchallenges.fyi/challenges/challenge-shell/:
prompt loop, external commands with arguments, builtins cd/pwd/exit/
history, pipes, SIGINT ignored by the shell (restored in children),
and history saved to ~/.ccsh_history on exit and reloaded on start.

Python 3 standard library only. External programs run via subprocess,
never reimplemented. No redirection, globbing, variables, or scripts:
the challenge page does not ask for them (see docs/SPEC.md).
"""

import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path

PROMPT = "ccsh> "
HISTORY_FILENAME = ".ccsh_history"
BUILTINS = ("cd", "pwd", "history", "exit")


def history_file_path():
    """History file: CCSH_HISTORY_FILE override, else ~/.ccsh_history."""
    override = os.environ.get("CCSH_HISTORY_FILE")
    if override:
        return Path(override)
    return Path.home() / HISTORY_FILENAME


def load_history(path):
    """Return saved history lines; missing/unreadable file -> []."""
    try:
        with open(path, encoding="utf-8") as f:
            return [line.rstrip("\n") for line in f if line.rstrip("\n")]
    except OSError:
        return []


def save_history(path, history):
    """Write history, one command per line. Never raise: a history
    failure must not kill the shell or mask its exit code."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            for line in history:
                f.write(line + "\n")
    except OSError as exc:
        print(f"ccsh: cannot save history to {path}: {exc}", file=sys.stderr)


def split_pipeline(line):
    """Split on unquoted '|' characters.

    Single quotes, double quotes, and backslash escapes protect a
    '|', so echo "a|b" is one command. Raises ValueError on an
    unterminated quote.
    """
    segments = []
    current = []
    quote = None
    escaped = False
    for ch in line:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\" and quote != "'":
            # Keep the backslash: shlex needs it to parse the segment.
            current.append(ch)
            escaped = True
        elif quote is not None:
            current.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            current.append(ch)
            quote = ch
        elif ch == "|":
            segments.append("".join(current))
            current = []
        else:
            current.append(ch)
    if quote is not None:
        raise ValueError("unterminated quote")
    segments.append("".join(current))
    return segments


def parse_command(segment):
    """shlex-split one pipeline segment. Raises ValueError on bad syntax."""
    try:
        return shlex.split(segment)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def run_builtin(argv, history):
    """Run a builtin. Returns (should_exit, exit_code), or None if
    argv[0] is not a builtin. Single-command context only; pipelines
    handle builtins separately (see run_pipeline)."""
    name = argv[0]
    if name == "cd":
        if len(argv) > 2:
            print("cd: too many arguments", file=sys.stderr)
        else:
            target = argv[1] if len(argv) == 2 else os.environ.get("HOME")
            if target is None:
                print("cd: HOME not set", file=sys.stderr)
            else:
                try:
                    os.chdir(target)
                except OSError as exc:
                    print(f"cd: {target}: {exc.strerror}", file=sys.stderr)
        return (False, 0)
    if name == "pwd":
        print(os.getcwd())
        return (False, 0)
    if name == "history":
        for line in history:
            print(line)
        return (False, 0)
    if name == "exit":
        if len(argv) > 2:
            print("exit: too many arguments", file=sys.stderr)
            return (False, 0)
        if len(argv) == 2:
            try:
                return (True, int(argv[1]))
            except ValueError:
                print(f"exit: {argv[1]}: numeric argument required",
                      file=sys.stderr)
                return (False, 0)
        return (True, 0)
    return None


def run_external(argv):
    """Run one external command, waiting for it. Errors never raise."""
    try:
        proc = subprocess.Popen(argv)
    except FileNotFoundError:
        print("No such file or directory (os error 2)", file=sys.stderr)
    except OSError as exc:
        print(exc.strerror or str(exc), file=sys.stderr)
    else:
        proc.wait()


def run_pipeline(segment_argvs):
    """Run a |-chained pipeline of external commands, waiting for all.

    `pwd` as a stage runs as the external pwd program, which inherits
    the shell's working directory, so its output is identical. Any
    other builtin in a pipeline is rejected before anything runs.
    """
    for argv in segment_argvs:
        if argv[0] in BUILTINS and argv[0] != "pwd":
            print(f"ccsh: {argv[0]}: builtin not supported in a pipeline",
                  file=sys.stderr)
            return
    processes = []
    prev_stdout = None
    try:
        for argv in segment_argvs:
            try:
                proc = subprocess.Popen(argv, stdin=prev_stdout,
                                        stdout=subprocess.PIPE
                                        if argv is not segment_argvs[-1]
                                        else None)
            except FileNotFoundError:
                print("No such file or directory (os error 2)",
                      file=sys.stderr)
                break
            except OSError as exc:
                print(exc.strerror or str(exc), file=sys.stderr)
                break
            processes.append(proc)
            # Hand the read end to the next stage; close our copy so
            # an early-exiting stage gives the previous one SIGPIPE.
            if prev_stdout is not None:
                prev_stdout.close()
            prev_stdout = proc.stdout
    finally:
        if prev_stdout is not None:
            prev_stdout.close()
    for proc in processes:
        proc.wait()


def run_line(line, history):
    """Execute one input line. Returns (should_exit, exit_code)."""
    stripped = line.strip()
    if not stripped:
        return (False, 0)
    try:
        segments = split_pipeline(stripped)
        segment_argvs = [parse_command(seg) for seg in segments]
    except ValueError as exc:
        print(f"ccsh: syntax error: {exc}", file=sys.stderr)
        return (False, 0)
    if any(not argv for argv in segment_argvs):
        print("ccsh: syntax error: empty command in pipeline",
              file=sys.stderr)
        return (False, 0)
    # The history builtin is never recorded (see docs/DESIGN.md).
    if not (len(segment_argvs) == 1 and segment_argvs[0][0] == "history"):
        history.append(stripped)
    if len(segment_argvs) == 1:
        argv = segment_argvs[0]
        builtin = run_builtin(argv, history)
        if builtin is not None:
            return builtin
        run_external(argv)
        return (False, 0)
    run_pipeline(segment_argvs)
    return (False, 0)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args:
        print("usage: python3 shell.py", file=sys.stderr)
        return 2
    # Step 7: ignore SIGINT in the shell itself. subprocess restores
    # the default disposition in children, so they still die on ^C.
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError):
        pass  # not the main thread, or platform without SIGINT: carry on
    hist_path = history_file_path()
    history = load_history(hist_path)

    use_readline = False
    if sys.stdin.isatty():
        try:
            import readline  # noqa: F401  (side effect: line editing)
            for line in history:
                readline.add_history(line)
            use_readline = True
        except ImportError:
            use_readline = False

    exit_code = 0
    try:
        while True:
            try:
                if use_readline:
                    line = input(PROMPT)
                else:
                    sys.stdout.write(PROMPT)
                    sys.stdout.flush()
                    line = sys.stdin.readline()
                    if line == "":
                        break  # EOF
            except EOFError:
                break
            except KeyboardInterrupt:
                # ^C with a handler installed (some platforms): new prompt.
                print()
                continue
            should_exit, exit_code = run_line(line, history)
            if should_exit:
                break
    finally:
        # Saved on every exit path: exit builtin, EOF, Ctrl-D.
        save_history(hist_path, history)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
