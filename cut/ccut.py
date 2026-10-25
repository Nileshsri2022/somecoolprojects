#!/usr/bin/env python3
"""cut - Build Your Own cut Tool (Coding Challenges #4), field mode.

Usage:
  ccut.py -f LIST [-d DELIM] [FILE ...]

Field list: N, N-M, N-, -M, separated by commas and/or
whitespace. Fields are numbered from 1. Default delimiter
is tab. No file, or file "-", means stdin.

Behaviour matches GNU cut where it was checked (see
docs/SPEC.md): selected fields come out in line order with
duplicates collapsed, a line without the delimiter is
printed whole, and every output line ends with a newline.

Python standard library only, single file. Works on bytes
so non-UTF-8 input cannot break decoding.
"""

import argparse
import re
import sys

# No ^/$ anchors: this regex is matched at a position inside
# the list, so a token must end where the separator starts,
# not where the whole string ends.
ITEM_RE = re.compile(r"(\d+)-(\d+)|(\d+)-|-(\d+)|(\d+)")


class CutError(Exception):
    pass


def parse_field_list(spec):
    """Parse a -f list into (selected_set, open_ended_from).

    selected_set holds explicitly selected field numbers.
    open_ended_from is the smallest N of any "N-" item, or
    None. A field is selected if it is in the set or >=
    open_ended_from.
    """
    selected = set()
    open_ended_from = None
    # Tokenise by hand, matching GNU cut's separator rules as
    # checked on this machine: a comma or a single space
    # separates items. "1,,2", "1, 2" and "1  2" are all
    # rejected by GNU cut, so they are rejected here too.
    if not spec:
        raise CutError("invalid field value ''")
    tokens = []
    pos = 0
    while pos < len(spec):
        match = ITEM_RE.match(spec, pos)
        if not match:
            raise CutError(f"invalid field value {spec!r}")
        tokens.append(spec[pos:match.end()])
        pos = match.end()
        if pos == len(spec):
            break
        if spec[pos] in (",", " "):
            pos += 1
            if pos == len(spec):
                raise CutError(f"invalid field value {spec!r}")
        else:
            raise CutError(f"invalid field value {spec!r}")
    for token in tokens:
        match = ITEM_RE.match(token)
        if not match:
            raise CutError(f"invalid field value {token!r}")
        lo, hi, lo_open, hi_closed, single = match.groups()
        if single is not None:
            num = int(single)
            if num == 0:
                raise CutError("fields are numbered from 1")
            selected.add(num)
        elif hi_closed is not None:
            num = int(hi_closed)
            if num == 0:
                raise CutError("fields are numbered from 1")
            selected.update(range(1, num + 1))
        elif lo_open is not None:
            num = int(lo_open)
            if num == 0:
                raise CutError("fields are numbered from 1")
            if open_ended_from is None or num < open_ended_from:
                open_ended_from = num
        else:
            lo, hi = int(lo), int(hi)
            if lo == 0 or hi == 0:
                raise CutError("fields are numbered from 1")
            if lo > hi:
                raise CutError("invalid decreasing range")
            selected.update(range(lo, hi + 1))
    return selected, open_ended_from


def cut_line(line, delim, selected, open_ended_from):
    """Cut one line (without its trailing newline) and return
    the output line, also without a trailing newline."""
    if delim not in line:
        return line
    fields = line.split(delim)
    out = [field for i, field in enumerate(fields, start=1)
           if i in selected
           or (open_ended_from is not None and i >= open_ended_from)]
    return delim.join(out)


def cut_stream(in_stream, out_stream, delim, selected, open_ended_from):
    for raw in in_stream:
        line = raw[:-1] if raw.endswith(b"\n") else raw
        out_stream.write(cut_line(line, delim, selected,
                                  open_ended_from) + b"\n")


def main(argv):
    parser = argparse.ArgumentParser(
        prog="ccut.py",
        description="Cut out selected fields from each line.")
    parser.add_argument("-f", required=True, metavar="LIST",
                        help="fields to select, e.g. 1,2 or '1 2' or 2-4")
    parser.add_argument("-d", default="\t", metavar="DELIM",
                        help="field delimiter, a single character (default: tab)")
    parser.add_argument("files", nargs="*", help="input files, '-' means stdin")
    args = parser.parse_args(argv)

    if len(args.d) != 1:
        print("ccut: the delimiter must be a single character",
              file=sys.stderr)
        return 1
    delim = args.d.encode("utf-8")
    try:
        selected, open_ended_from = parse_field_list(args.f)
    except CutError as exc:
        print(f"ccut: {exc}", file=sys.stderr)
        return 1

    files = args.files if args.files else ["-"]
    exit_code = 0
    out = sys.stdout.buffer
    for path in files:
        try:
            if path == "-":
                cut_stream(sys.stdin.buffer, out, delim,
                           selected, open_ended_from)
            else:
                with open(path, "rb") as f:
                    cut_stream(f, out, delim, selected, open_ended_from)
        except OSError as exc:
            print(f"ccut: {path}: {exc.strerror}", file=sys.stderr)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
