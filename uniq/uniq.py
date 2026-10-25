#!/usr/bin/env python3
"""uniq: filter adjacent duplicate lines (Coding Challenges #10).

Reads lines, compares only adjacent ones, and writes one copy of
each run of identical lines. Options: -c/--count, -d/--repeated,
-u/--unique (combinable). Input is a file, '-' or absent (stdin);
an optional second argument is the output file, else stdout.

Bytes throughout: comparison key is the line minus a trailing
newline only, so CRLF endings and non-UTF-8 bytes round-trip.
Output lines are key + newline, matching GNU: a final input
line without a newline gains one on output.
"""

import argparse
import sys


def key_of(line):
    """Comparison key: line without its trailing newline, if any."""
    if line.endswith(b"\n"):
        return line[:-1]
    return line


def keep_run(count, repeated, unique):
    """Whether a run of `count` lines passes the -d/-u filter."""
    if repeated and count == 1:
        return False
    if unique and count > 1:
        return False
    return True


def emit(out, key, count, show_count, repeated, unique):
    """Write one run if it passes the filter.

    The line is emitted as key + newline: GNU uniq adds a
    trailing newline to a final unterminated input line,
    and a CRLF line's key still carries its \\r, so CRLF
    round-trips exactly.
    """
    if not keep_run(count, repeated, unique):
        return
    if show_count:
        out.write(b"%7d " % count)
    out.write(key + b"\n")


def run_uniq(inp, out, show_count, repeated, unique):
    """Stream inp to out, collapsing adjacent duplicate lines."""
    prev_key = None
    count = 0
    for line in inp:
        key = key_of(line)
        if prev_key is not None and key == prev_key:
            count += 1
        else:
            if prev_key is not None:
                emit(out, prev_key, count, show_count, repeated, unique)
            prev_key, count = key, 1
    if prev_key is not None:
        emit(out, prev_key, count, show_count, repeated, unique)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="uniq",
        description="Filter adjacent duplicate lines.",
    )
    parser.add_argument("-c", "--count", action="store_true",
                        help="prefix lines by the number of occurrences")
    parser.add_argument("-d", "--repeated", action="store_true",
                        help="only print duplicate lines, one per run")
    parser.add_argument("-u", "--unique", action="store_true",
                        help="only print lines that occur exactly once")
    # All positionals collected, so a third one can be reported
    # GNU-style (exit 1) instead of argparse's exit 2.
    parser.add_argument("files", nargs="*",
                        help="input file (or - / omitted for stdin) "
                        "and optional output file")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if len(args.files) > 2:
        print(f"uniq: extra operand '{args.files[2]}'", file=sys.stderr)
        print("Try 'uniq --help' for more information.", file=sys.stderr)
        return 1
    input_name = args.files[0] if args.files else "-"
    output_name = args.files[1] if len(args.files) > 1 else None
    if input_name == "-":
        inp = sys.stdin.buffer
    else:
        try:
            inp = open(input_name, "rb")
        except OSError as exc:
            print(f"uniq: {input_name}: {exc.strerror}",
                  file=sys.stderr)
            return 1
    try:
        if output_name is None:
            out = sys.stdout.buffer
            run_uniq(inp, out, args.count, args.repeated, args.unique)
        else:
            try:
                out = open(output_name, "wb")
            except OSError as exc:
                print(f"uniq: {output_name}: {exc.strerror}",
                      file=sys.stderr)
                return 1
            with out:
                run_uniq(inp, out, args.count, args.repeated, args.unique)
    finally:
        if inp is not sys.stdin.buffer:
            inp.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
