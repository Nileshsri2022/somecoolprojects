#!/usr/bin/env python3
"""ccat: concatenate files (and standard input) to standard output.

Coding Challenges #15 (Build Your Own cat Tool). Python 3 standard
library only, bytes throughout so binary input passes through verbatim.

Usage: cat.py [-n | -b] [file ...]
  No operands, or "-" as an operand, reads standard input.
  -n numbers every line, -b numbers only non-blank lines;
  if both are given, -b wins (as with system cat).
  Numbering continues across concatenated files.
"""

import sys

CHUNK = 8192


def parse_args(argv):
    """Return (number_mode, operands); number_mode is None, "n", or "b".

    Raises ValueError("ccat: invalid option -- 'x'") on an unknown option.
    Options may appear before, between, or after operands; "--" ends
    option parsing; a lone "-" is always stdin, never an option.
    """
    mode = None
    operands = []
    options_done = False
    for arg in argv:
        if not options_done and arg == "--":
            options_done = True
        elif not options_done and arg.startswith("-") and arg != "-":
            for ch in arg[1:]:
                if ch == "n":
                    if mode != "b":
                        mode = "n"
                elif ch == "b":
                    mode = "b"
                else:
                    raise ValueError(f"ccat: invalid option -- '{ch}'")
        else:
            operands.append(arg)
    return mode, operands


def copy_stream(in_stream, out_stream, mode, state):
    """Copy in_stream to out_stream; state[0] is the next line number."""
    if mode is None:
        while True:
            chunk = in_stream.read(CHUNK)
            if not chunk:
                break
            out_stream.write(chunk)
        return
    for line in in_stream:
        if mode == "b" and line == b"\n":
            out_stream.write(line)
        else:
            out_stream.write(f"{state[0]:6d}\t".encode("ascii"))
            out_stream.write(line)
            state[0] += 1


def main(argv):
    try:
        mode, operands = parse_args(argv)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not operands:
        operands = ["-"]
    exit_code = 0
    state = [1]
    out = sys.stdout.buffer
    for path in operands:
        if path == "-":
            copy_stream(sys.stdin.buffer, out, mode, state)
            continue
        try:
            stream = open(path, "rb")
        except OSError as exc:
            print(f"ccat: {path}: {exc.strerror}", file=sys.stderr)
            exit_code = 1
            continue
        with stream:
            copy_stream(stream, out, mode, state)
    out.flush()
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
