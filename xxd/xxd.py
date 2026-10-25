#!/usr/bin/env python3
"""xxd clone: hex dump and reverse (hex dump -> binary).

Implements Coding Challenges "Build Your Own Xxd" (slug: challenge-xxd),
Steps 1-5: default dump, -e little-endian, -g grouping, -c columns,
-l length, -s seek, -r reverse. Python 3 standard library only.

Usage:
    python3 xxd.py [-e] [-g GROUP] [-c COLS] [-l LENGTH] [-s OFFSET]
                   [-r] [infile [outfile]]
No infile means stdin; no outfile means stdout.
"""

import argparse
import io
import re
import sys

MAX_COLS = 256
MAX_GROUP = 256
OFFSET_RE = re.compile(r"^[0-9a-fA-F]+:\s*")


class XxdError(Exception):
    """User-facing error: message goes to stderr, exit code 1."""


def parse_number(value, name):
    """Parse a decimal or 0x-prefixed integer, with optional +/- sign."""
    try:
        return int(value, 0)
    except ValueError:
        raise XxdError(f"xxd: invalid {name}: {value!r}")


def parse_groupsize(value):
    """Group size must be a power of two in 1..MAX_GROUP."""
    n = parse_number(value, "grouping")
    if n < 1 or n > MAX_GROUP or (n & (n - 1)) != 0:
        raise XxdError(
            f"xxd: invalid grouping: {value!r} "
            f"(must be a power of two between 1 and {MAX_GROUP})"
        )
    return n


def parse_cols(value):
    n = parse_number(value, "columns")
    if n < 1 or n > MAX_COLS:
        raise XxdError(
            f"xxd: invalid columns: {value!r} "
            f"(must be between 1 and {MAX_COLS})"
        )
    return n


def parse_length(value):
    n = parse_number(value, "length")
    if n < 0:
        raise XxdError(f"xxd: invalid length: {value!r} (must be >= 0)")
    return n


def full_hex_width(cols, groupsize):
    """Width of a full line's hex field for these cols/groupsize."""
    groups = (cols + groupsize - 1) // groupsize
    return cols * 2 + (groups - 1)


def format_line(offset, chunk, cols, groupsize, little_endian):
    """Format one dump line. chunk is <= cols bytes."""
    groups = []
    for start in range(0, len(chunk), groupsize):
        group = chunk[start:start + groupsize]
        if little_endian:
            group = group[::-1]
        groups.append(group.hex())
    hex_field = " ".join(groups)
    hex_field = hex_field.ljust(full_hex_width(cols, groupsize))
    ascii_field = "".join(
        chr(b) if 0x20 <= b <= 0x7E else "." for b in chunk
    )
    return f"{offset:08x}: {hex_field}  {ascii_field}\n"


def dump(in_stream, out_stream, cols, groupsize, little_endian,
         length, seek):
    """Write a hex dump of in_stream to out_stream (text)."""
    if seek is not None and seek < 0:
        # Negative seek = before EOF. Only possible after reading all
        # input; this is the one whole-input read in the program.
        data = in_stream.read()
        start = max(0, len(data) + seek)
        in_stream = io.BytesIO(data[start:])
        offset = start
    else:
        offset = 0
        if seek:
            try:
                in_stream.seek(seek)
                offset = seek
            except (OSError, io.UnsupportedOperation):
                # Non-seekable stream (pipe): discard `seek` bytes.
                remaining = seek
                while remaining > 0:
                    skipped = in_stream.read(min(remaining, 65536))
                    if not skipped:
                        break
                    remaining -= len(skipped)
                offset = seek - remaining
    remaining = length  # None means unlimited
    while remaining is None or remaining > 0:
        want = cols if remaining is None else min(cols, remaining)
        chunk = in_stream.read(want)
        if not chunk:
            break
        out_stream.write(
            format_line(offset, chunk, cols, groupsize, little_endian)
        )
        offset += len(chunk)
        if remaining is not None:
            remaining -= len(chunk)


def revert_line(line):
    """Parse one dump line into bytes. Raises XxdError on bad hex."""
    line = line.strip()
    if not line:
        return b""
    line = OFFSET_RE.sub("", line, count=1)
    # Only the first segment is hex; anything after two or more
    # spaces is the ASCII column and is ignored.
    hex_segment = re.split(r"\s{2,}", line.strip(), maxsplit=1)[0]
    if not hex_segment:
        return b""
    out = bytearray()
    for token in hex_segment.split():
        if len(token) % 2 != 0 or not all(c in "0123456789abcdefABCDEF"
                                          for c in token):
            raise XxdError(f"xxd: invalid hex in input line: {line!r}")
        out.extend(bytes.fromhex(token))
    return bytes(out)


def revert(in_stream, out_stream, groupsize, little_endian,
           length, seek):
    """Convert a hex dump (text stream) back to binary."""
    if seek:
        if seek > 0:
            try:
                out_stream.seek(seek)
            except (OSError, io.UnsupportedOperation):
                out_stream.write(b"\x00" * seek)
        # Negative seek in reverse mode is not meaningful; ignore it
        # (real xxd -r -s with a negative value is undefined here).
    remaining = length
    for raw in in_stream:
        line = raw.decode("ascii", errors="strict") \
            if isinstance(raw, bytes) else raw
        chunk = revert_line(line)
        if little_endian and groupsize > 1:
            fixed = bytearray()
            for start in range(0, len(chunk), groupsize):
                fixed.extend(chunk[start:start + groupsize][::-1])
            chunk = bytes(fixed)
        if remaining is not None:
            chunk = chunk[:remaining]
            remaining -= len(chunk)
        out_stream.write(chunk)
        if remaining == 0:
            break


def build_parser():
    parser = argparse.ArgumentParser(
        prog="xxd",
        description="Make a hex dump, or convert a hex dump back "
                    "to binary (-r).",
    )
    parser.add_argument("-e", dest="little_endian", action="store_true",
                        help="little-endian: reverse bytes in each group")
    parser.add_argument("-g", dest="groupsize", default=None,
                        help="number of octets per group "
                             "(power of two, default 2, or 4 with -e)")
    parser.add_argument("-c", dest="cols", default=None,
                        help="bytes per line (1-256, default 16)")
    parser.add_argument("-l", dest="length", default=None,
                        help="number of bytes to dump/restore")
    parser.add_argument("-s", dest="seek", default=None,
                        help="seek offset: decimal, 0x hex, or negative "
                             "(bytes before EOF, forward dump only)")
    parser.add_argument("-r", dest="reverse", action="store_true",
                        help="reverse operation: hex dump to binary")
    parser.add_argument("infile", nargs="?", default=None)
    parser.add_argument("outfile", nargs="?", default=None)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        groupsize = (parse_groupsize(args.groupsize)
                     if args.groupsize is not None
                     else (4 if args.little_endian else 2))
        cols = parse_cols(args.cols) if args.cols is not None else 16
        length = (parse_length(args.length)
                  if args.length is not None else None)
        seek = (parse_number(args.seek, "seek offset")
                if args.seek is not None else None)
    except XxdError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.infile in (None, "-"):
        in_stream = sys.stdin.buffer
    else:
        try:
            in_stream = open(args.infile, "rb")
        except OSError as exc:
            print(f"xxd: {args.infile}: {exc.strerror}", file=sys.stderr)
            return 1
    if args.outfile is None:
        out_stream = sys.stdout.buffer if args.reverse else sys.stdout
        close_out = False
    else:
        try:
            out_stream = open(args.outfile, "wb")
        except OSError as exc:
            print(f"xxd: {args.outfile}: {exc.strerror}", file=sys.stderr)
            if in_stream is not sys.stdin.buffer:
                in_stream.close()
            return 1
        close_out = True

    try:
        if args.reverse:
            # Revert reads text; wrap a binary stream in a text reader.
            text_in = (in_stream if isinstance(in_stream, io.TextIOBase)
                       else io.TextIOWrapper(in_stream, encoding="ascii",
                                             errors="strict"))
            revert(text_in, out_stream, groupsize, args.little_endian,
                   length, seek)
        else:
            text_out = io.TextIOWrapper(out_stream, encoding="ascii",
                                        write_through=True) \
                if isinstance(out_stream, io.BufferedIOBase) else out_stream
            dump(in_stream, text_out, cols, groupsize,
                 args.little_endian, length, seek)
            if isinstance(out_stream, io.BufferedIOBase):
                text_out.flush()
    except (XxdError, UnicodeDecodeError) as exc:
        print(f"xxd: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 1
    finally:
        if in_stream is not sys.stdin.buffer:
            in_stream.close()
        if close_out:
            out_stream.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
