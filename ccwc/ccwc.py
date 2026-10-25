#!/usr/bin/env python3
"""ccwc - Build Your Own wc Tool (Coding Challenges #1).

Usage: ccwc.py [-c] [-l] [-w] [-m] [file ...]
  No file: read stdin. No option: -l -w -c, in that order.
  Python 3, standard library only. Input is streamed in 8 KiB
  chunks, so memory stays constant regardless of file size.

See docs/SPEC.md for the counting rules and the one deliberate
difference from GNU wc: -m always counts UTF-8 code points,
whereas GNU wc -m in a C locale equals -c.
"""

import codecs
import sys

WHITESPACE = b" \t\n\v\f\r"
CHUNK = 8192


def count_stream(stream):
    """Return (lines, words, bytes, chars) for a binary stream."""
    lines = words = nbytes = nchars = 0
    in_word = False
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    while True:
        chunk = stream.read(CHUNK)
        if not chunk:
            break
        nbytes += len(chunk)
        lines += chunk.count(b"\n")
        nchars += len(decoder.decode(chunk))
        for byte in chunk:
            if byte in WHITESPACE:
                in_word = False
            elif not in_word:
                words += 1
                in_word = True
    nchars += len(decoder.decode(b"", final=True))
    return lines, words, nbytes, nchars


def parse_args(argv):
    """Return (options, files). options is a list like ['l', 'w', 'c']."""
    options = []
    files = []
    for arg in argv:
        if arg.startswith("-") and arg != "-" and not files:
            for flag in arg[1:]:
                if flag not in "clwm":
                    raise ValueError(f"ccwc: invalid option -- '{flag}'")
                if flag not in options:
                    options.append(flag)
        else:
            files.append(arg)
    if not options:
        options = ["l", "w", "c"]
    else:
        # Output order is always lines, words, bytes, chars,
        # regardless of flag order on the command line.
        order = {"l": 0, "w": 1, "c": 2, "m": 3}
        options.sort(key=lambda f: order[f])
    return options, files


def format_line(counts, options, width, label):
    picked = [counts[{"l": 0, "w": 1, "c": 2, "m": 3}[opt]]
              for opt in options]
    text = " ".join(str(c).rjust(width) for c in picked)
    return f"{text} {label}" if label else text


def main(argv):
    try:
        options, files = parse_args(argv)
    except ValueError as exc:
        print(f"{exc}\nusage: ccwc.py [-c] [-l] [-w] [-m] [file ...]",
              file=sys.stderr)
        return 1

    results = []  # (counts, label)
    if not files:
        counts = count_stream(sys.stdin.buffer)
        width = 7 if len(options) > 1 else len(str(max(
            counts[{"l": 0, "w": 1, "c": 2, "m": 3}[opt]]
            for opt in options)))
        print(format_line(counts, options, width, ""))
        return 0

    failed = False
    for path in files:
        try:
            with open(path, "rb") as stream:
                results.append((count_stream(stream), path))
        except OSError as exc:
            print(f"ccwc: {path}: {exc.strerror}", file=sys.stderr)
            failed = True

    if not results:
        return 1

    all_counts = [counts for counts, _ in results]
    if len(results) > 1:
        total = tuple(sum(c[i] for c in all_counts) for i in range(4))
        all_counts.append(total)
    index = {"l": 0, "w": 1, "c": 2, "m": 3}
    if len(options) > 1:
        # GNU wc pads multi-count output to the width of the
        # total byte count (sum over all files), not to the
        # largest displayed count. Verified: two 5000-byte files
        # print with width 5 (total 10000 bytes), one 5000-byte
        # file alone prints with width 4.
        total_bytes = sum(counts[2] for counts, _ in results)
        width = len(str(total_bytes))
    else:
        width = max(len(str(c[index[opt]]))
                      for c in all_counts for opt in options)
    for counts, label in results:
        print(format_line(counts, options, width, label))
    if len(results) > 1:
        print(format_line(total, options, width, "total"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
