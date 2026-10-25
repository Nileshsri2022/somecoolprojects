#!/usr/bin/env python3
"""grep.py — Build Your Own grep (Coding Challenges #9).

Searches input lines for a regular expression (Python `re`, ERE-like),
printing each matching line. Supports the options on the challenge
page only: -r (recurse), -v (invert), -i (ignore case).

Usage: grep.py [-riv] [--] PATTERN [FILE ...]
  No FILE: read standard input.  '-' as a FILE: standard input.
Exit codes: 0 match found, 1 no match, 2 error.
"""

import os
import re
import sys

PROG = "grep.py"
STDIN_NAME = "(standard input)"


class UsageError(Exception):
    """Bad command line: message is printed, exit code is 2."""


def parse_args(argv):
    """Return (pattern, files, recursive, invert, ignore_case).

    The first non-option argument is the pattern; the rest are files.
    Option bundles like -ri are accepted; -- ends option parsing.
    """
    recursive = invert = ignore_case = False
    pattern = None
    files = []
    end_of_options = False
    for arg in argv:
        if pattern is None and not end_of_options and arg.startswith("-") and arg != "-":
            if arg == "--":
                end_of_options = True
                continue
            for ch in arg[1:]:
                if ch == "r":
                    recursive = True
                elif ch == "v":
                    invert = True
                elif ch == "i":
                    ignore_case = True
                else:
                    raise UsageError("invalid option -- '%s'" % ch)
        elif pattern is None:
            pattern = arg
        else:
            files.append(arg)
    if pattern is None:
        raise UsageError("missing pattern\nUsage: %s [-riv] [--] PATTERN [FILE ...]" % PROG)
    return pattern, files, recursive, invert, ignore_case


def compile_pattern(pattern, ignore_case):
    """Compile the pattern as a bytes regex; re.error -> UsageError."""
    flags = re.IGNORECASE if ignore_case else 0
    try:
        return re.compile(os.fsencode(pattern), flags)
    except re.error as exc:
        raise UsageError("invalid pattern %r: %s" % (pattern, exc))


def iter_inputs(files, recursive, errors):
    """Yield (display_name, binary_stream) for each input.

    display_name is None for a lone stdin input (no prefix printed).
    Returns (inputs, saw_directory): saw_directory is True when any
    directory operand was recursed (GNU prefixes those matches even
    when the directory yields a single file). With -r and no file
    operands, GNU recurses the working directory, printing paths
    without the leading './'.
    Errors are appended to `errors` and the input is skipped, so one
    bad file does not stop the rest — as with GNU grep.
    """
    inputs = []
    saw_directory = False
    if not files:
        if recursive:
            files = ["."]
            implicit_dot = True
        else:
            return [(None, sys.stdin.buffer)], False
    else:
        implicit_dot = False
    for path in files:
        if path == "-":
            inputs.append((STDIN_NAME, sys.stdin.buffer))
        elif os.path.isdir(path):
            if not recursive:
                errors.append("%s: Is a directory" % path)
                continue
            saw_directory = True
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames.sort()
                for name in sorted(filenames):
                    full = os.path.join(dirpath, name)
                    if implicit_dot and full.startswith("./"):
                        full = full[2:]
                    try:
                        inputs.append((full, open(full, "rb")))
                    except OSError as exc:
                        errors.append("%s: %s" % (full, exc.strerror or exc))
        else:
            try:
                inputs.append((path, open(path, "rb")))
            except OSError as exc:
                errors.append("%s: %s" % (path, exc.strerror or exc))
    return inputs, saw_directory


def search_stream(stream, regex, invert, prefix, out):
    """Print matching lines from stream; return True if any matched."""
    matched_any = False
    for line in stream:
        content = line[:-1] if line.endswith(b"\n") else line
        matched = regex.search(content) is not None
        if invert:
            matched = not matched
        if matched:
            matched_any = True
            if prefix is not None:
                out.write(os.fsencode(prefix) + b":")
            out.write(line if line.endswith(b"\n") else line + b"\n")
    return matched_any


def main(argv):
    try:
        pattern, files, recursive, invert, ignore_case = parse_args(argv)
        regex = compile_pattern(pattern, ignore_case)
    except UsageError as exc:
        print("%s: %s" % (PROG, exc), file=sys.stderr)
        return 2

    errors = []
    inputs, saw_directory = iter_inputs(files, recursive, errors)
    # Prefix when more than one file operand was given (GNU counts
    # operands, not successfully opened files: a missing file still
    # makes the other file's matches prefixed), or when a directory
    # was recursed (GNU prefixes those matches even if it yields one
    # file).
    use_prefix = saw_directory or len(files) > 1
    out = sys.stdout.buffer
    matched_any = False
    for name, stream in inputs:
        try:
            if search_stream(stream, regex, invert, name if use_prefix else None, out):
                matched_any = True
        finally:
            if stream is not sys.stdin.buffer:
                stream.close()
    for error in errors:
        print("%s: %s" % (PROG, error), file=sys.stderr)
    if errors:
        return 2
    return 0 if matched_any else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
