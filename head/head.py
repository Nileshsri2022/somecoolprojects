#!/usr/bin/env python3
"""head: print the first N lines (default 10) or N bytes of files/stdin.

Bytes throughout, so binary input and a final line without a
trailing newline pass through verbatim. See docs/SPEC.md.
Python 3 standard library only.
"""

import errno
import signal
import sys
from collections import deque

PROG = "head"
DEFAULT_LINES = 10
CHUNK = 8192

USAGE = """Usage: head [OPTION]... [FILE]...
Print the first 10 lines of each FILE to standard output.
With more than one FILE, precede each with a header giving the file name.

  -c, --bytes=NUM   print the first NUM bytes of each file
  -n, --lines=NUM   print the first NUM lines instead of the first 10;
                    with a leading '-', print all but the last NUM lines
  -q, --quiet       never print headers giving file names
  -v, --verbose     always print headers giving file names
      --help        display this help and exit
"""


class HeadError(Exception):
    """Usage error: message already in GNU head style, exit status 1."""


def parse_count(text, kind):
    """Return (count, negative): int() alone would lose '-0'.

    Negative counts mean "all but the last N"; '-0' therefore
    means "all", unlike plain 0 which means "none".
    """
    body = text[1:] if text.startswith("+") else text
    negative = body.startswith("-")
    digits = body[1:] if negative else body
    if not digits or not digits.isdigit():
        raise HeadError(f"{PROG}: invalid number of {kind}: '{text}'")
    return int(digits), negative


def parse_args(argv):
    mode = "lines"
    count = DEFAULT_LINES
    negative = False
    verbose = False
    quiet = False
    operands = []
    i = 0
    end_of_options = False
    while i < len(argv):
        arg = argv[i]
        if end_of_options or not arg.startswith("-") or arg == "-":
            operands.append(arg)
            i += 1
            continue
        if arg == "--":
            end_of_options = True
            i += 1
            continue
        if arg == "--help":
            sys.stdout.write(USAGE)
            raise SystemExit(0)
        if arg.startswith("--lines="):
            count, negative = parse_count(arg[len("--lines="):], "lines")
            mode = "lines"
            i += 1
            continue
        if arg.startswith("--bytes="):
            count, negative = parse_count(arg[len("--bytes="):], "bytes")
            mode = "bytes"
            i += 1
            continue
        if arg in ("--lines", "--bytes"):
            kind = "lines" if arg == "--lines" else "bytes"
            if i + 1 >= len(argv):
                raise HeadError(
                    f"{PROG}: option requires an argument -- '{arg[2]}'")
            count, negative = parse_count(argv[i + 1], kind)
            mode = kind
            i += 2
            continue
        if arg == "--quiet":
            quiet = True
            i += 1
            continue
        if arg == "--verbose":
            verbose = True
            i += 1
            continue
        if arg.startswith("--"):
            raise HeadError(f"{PROG}: unrecognized option '{arg}'")
        # Short options, possibly clustered; n/c take a value.
        j = 1
        consumed_next = False
        while j < len(arg):
            opt = arg[j]
            if opt == "q":
                quiet = True
                j += 1
            elif opt == "v":
                verbose = True
                j += 1
            elif opt in ("n", "c"):
                kind = "lines" if opt == "n" else "bytes"
                # NB: short options take no '='; '-n=4' is an
                # invalid number '=4' to system head, and so here.
                rest = arg[j + 1:]
                if rest:
                    value = rest
                elif i + 1 < len(argv):
                    value = argv[i + 1]
                    consumed_next = True
                else:
                    raise HeadError(
                        f"{PROG}: option requires an argument -- '{opt}'")
                count, negative = parse_count(value, kind)
                mode = kind
                j = len(arg)
            elif opt.isdigit():
                # Obsolete form: head -2 file == head -n 2 file.
                count, negative = parse_count(arg[1:], "lines")
                mode = "lines"
                j = len(arg)
            else:
                raise HeadError(f"{PROG}: invalid option -- '{opt}'")
        i += 2 if consumed_next else 1
    return mode, count, negative, verbose, quiet, operands


def head_lines(stream, count, negative, out):
    if not negative:
        for _ in range(count):
            line = stream.readline()
            if not line:
                break
            out.write(line)
        return
    if count == 0:  # -0: everything
        for line in stream:
            out.write(line)
        return
    hold = deque(maxlen=count)
    for line in stream:
        if len(hold) == count:
            out.write(hold.popleft())
        hold.append(line)


def head_bytes(stream, count, negative, out):
    if not negative:
        remaining = count
        while remaining > 0:
            chunk = stream.read(min(CHUNK, remaining))
            if not chunk:
                break
            out.write(chunk)
            remaining -= len(chunk)
        return
    if count == 0:  # -0: everything
        while True:
            chunk = stream.read(CHUNK)
            if not chunk:
                break
            out.write(chunk)
        return
    buf = bytearray()
    while True:
        chunk = stream.read(CHUNK)
        if not chunk:
            break
        buf += chunk
        if len(buf) > count:
            out.write(bytes(buf[:len(buf) - count]))
            del buf[:len(buf) - count]


class _FailingStream:
    """A stream that fails on read, like a directory opened by C head.

    GNU head opens a directory successfully and fails on the
    first read, so its header is printed before the error.
    Python's open() refuses a directory outright, so this
    stand-in reproduces the read-failure path.
    """

    def _fail(self, *args):
        raise OSError(errno.EISDIR, "Is a directory")

    readline = _fail
    read = _fail

    def __iter__(self):
        self._fail()
        yield from ()


def process(stream, mode, count, negative, out):
    if mode == "lines":
        head_lines(stream, count, negative, out)
    else:
        head_bytes(stream, count, negative, out)


def main(argv):
    # Die on SIGPIPE like a C tool instead of raising BrokenPipeError.
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ValueError, OSError):
        pass
    try:
        mode, count, negative, verbose, quiet, operands = parse_args(argv)
    except HeadError as exc:
        print(exc, file=sys.stderr)
        return 1
    show_header = verbose or (len(operands) > 1 and not quiet)
    out = sys.stdout.buffer
    status = 0
    printed = False  # any header/content already written to stdout

    def run_one(stream, display_name):
        nonlocal printed, status
        if show_header:
            if printed:
                out.write(b"\n")
            out.write(f"==> {display_name} <==\n".encode())
            printed = True
        try:
            process(stream, mode, count, negative, out)
            printed = True
        except OSError as exc:
            print(f"{PROG}: error reading '{display_name}': "
                  f"{exc.strerror or exc}", file=sys.stderr)
            status = 1

    if not operands:
        try:
            if show_header:
                run_one(sys.stdin.buffer, "standard input")
            else:
                process(sys.stdin.buffer, mode, count, negative, out)
        except OSError as exc:
            print(f"{PROG}: error reading 'standard input': "
                  f"{exc.strerror or exc}", file=sys.stderr)
            status = 1
        return status

    for operand in operands:
        if operand == "-":
            run_one(sys.stdin.buffer, "standard input")
            continue
        try:
            stream = open(operand, "rb")
        except OSError as exc:
            if exc.errno == errno.EISDIR:
                run_one(_FailingStream(), operand)
                continue
            print(f"{PROG}: cannot open '{operand}' for reading: "
                  f"{exc.strerror or exc}", file=sys.stderr)
            status = 1
            continue
        with stream:
            run_one(stream, operand)
    try:
        out.flush()
    except OSError:
        pass
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
