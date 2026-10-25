# TEST_PLAN — CronTab Tool

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

No network, no system crontab, no installed packages. All
fixtures are in-memory strings or files in `tempfile`
directories created by the tests themselves.

## Coverage map (file: tests/test_crontab.py)

1. Parsing basics: `*`, single values, lists, ranges, steps
   (`*/15`, `1-10/2`, `5/15`), mixed lists, whitespace
   (tabs/multiple spaces) between fields.
2. Names: month names JAN–DEC and weekday names SUN–SAT,
   case-insensitive, full names and abbreviations, in values
   and in ranges (`MON-FRI`, `JAN-MAR`).
3. Day-of-week 7 == Sunday (normalised to 0); `0,7` collapses
   to `{0}`.
4. `@special` expansion: `@yearly`/`@annually` =
   `0 0 1 1 *`, `@monthly` = `0 0 1 * *`, `@weekly` =
   `0 0 * * 0`, `@daily`/`@midnight` = `0 0 * * *`,
   `@hourly` = `0 * * * *`; `@reboot` parses but has no
   next run.
5. Validation errors (each asserting the field name appears
   in the message): too few fields, out-of-range values
   per field, reversed ranges (`5-1`), step `0`, non-numeric
   step, unknown names (`FOO`, `JANUARYY`), empty list items
   (`1,,2`), unsupported `?`/`L`/`W`/`#`,
   unknown `@special`, empty input. (A six-token line is five
   fields plus a command, not an error — covered separately.)
6. Matching: exact match, minute/hour/month mismatch;
   dom/dow OR rule (both restricted -> either matches),
   dom-only and dow-only restriction, `*` in both;
   month-name schedules; the page example `0 9 * * 6`
   matches a Saturday 09:00 and not a Saturday 10:00 or a
   Friday 09:00.
7. Next runs: `*/15 * * * *` from a known moment (first three
   runs, strictly-after semantics — a run exactly at the
   reference moment is excluded); `0 9 * * 6` across a week
   boundary; `0 0 29 2 *` lands on the next leap day;
   impossible `31 2` raises after the cap (the test passes
   `max_years=1` to keep it fast; see note below).
8. Describe: page example contains "09:00" and "Saturday";
   `@daily` contains "00:00"; `*/5` contains "every 5
   minutes"; all-`*` says "every minute"; invalid input
   raises before describing.
9. Crontab files: comments, blank lines and `PATH=...` env
   lines skipped; commands with spaces preserved; an invalid
   line is collected in `errors` with its line number and
   does not abort parsing of later lines; `@daily` lines in
   files work.
10. CLI (via `subprocess`, temp files only): `explain`,
    `validate` (exit 0 valid / 2 invalid), `next`,
    `matches`, `list` (including `list -` from stdin), bare
    expression shorthand, unknown subcommand exit 1, and
    confirmation that no test invokes the system `crontab`
    binary at all (there is no code path that does).

Note on test 7's impossible-date case: `next_runs` takes a
`max_years` parameter (default 5) precisely so this case can
be tested fast (`max_years=1`, ~0.5M iterations) without
skipping it. The default 5-year scan is ~2.6M iterations.

## Success criteria

- All tests pass: `python3 -m unittest discover -s tests -v`.
- `python3 crontab.py "0 9 * * 6 send-newsletter"` prints an
  explanation containing Saturday and a next-run date.
- `python3 crontab.py validate "61 * * * *"` fails with a
  message naming the minute field.
- No `__pycache__` left in the delivered tree.
