# uniq — Test Plan

Test file: `tests/test_uniq.py`, run with
`python3 -m unittest discover -s tests -v` from the
`uniq/` directory. No network, no downloaded test
data: the page's Dropbox `countries.txt` is not
fetched; fixtures below cover the same behaviours
(including its step-1 shape) locally.

## Comparison oracle

Wherever behaviour is meant to match system uniq,
tests run both our `uniq.py` and system `uniq`
(GNU coreutils 9.4) on the same fixture bytes and
assert byte-for-byte equality of stdout (and, for
the `-c` cases, of the width-7 count format).
System uniq is invoked with the same option flags
and the same input file or piped stdin.

## Cases

1. Step 1 default: page example
   (`line1, line2, line2, line3, line4`).
2. Default on: empty input; single line; all lines
   identical (one run); no repeats at all; repeats
   NOT adjacent (must survive untouched); blank
   lines (run of blanks collapses to one blank).
3. Step 2 I/O: stdin via `-`, stdin via no argument,
   file argument, output-file argument (file input
   and stdin input), output file content equals
   stdout for the same input.
4. Step 3 `-c` and `--count`: page example, all-same
   input (one line, count = N), empty input.
5. Step 4 `-d` and `--repeated`: page example
   (only `line2`), input with no repeats (empty
   output), input where every line repeats.
6. Step 5 `-u` and `--unique`: page example
   (`line1, line3, line4`), input with no unique
   lines (empty output).
7. Step 6 combinations: `-c -d`, `-cd` (combined
   short flags), `-c -u`, `-d -u` (empty output,
   GNU behaviour), each compared against system uniq.
8. Byte fidelity: input with no trailing newline on
   the last line (GNU adds one — output ends with
   `\n`); CRLF lines (`a\r\n` vs `a\n` are distinct
   lines, `\r` preserved); non-UTF-8 bytes round-trip.
9. Errors: missing input file (exit 1, stderr names
   the file); extra operand (exit 1, stderr says
   `extra operand`); unknown option (exit 2).
   Missing-input must not truncate an output file
   argument (checked by pre-creating the output
   file and asserting its content is unchanged).
10. Unit-level: the run-filter function is tested
    directly for default / -d / -u / -d+-u on
    counts 1 and 2.

## Success criteria

All tests pass, and every system-comparison case
matches GNU uniq byte-for-byte. A deliberate,
documented divergence is the `-c` padding: the
page's illustration shows unpadded counts, but
tests assert GNU's width-7 format (see SPEC.md).
