# DESIGN — CronTab Tool

## Assumptions (stated before coding, ponytail rules)

1. The page's core is decode: parse + validate + explain. The
   brief's next-run / list / match features are a small, natural
   extension of the same parsed representation, not a second
   tool, so they share one parser.
2. One file, `crontab.py`, Python 3 standard library only. The
   parser is importable (`CronExpression`, `CronJob`,
   `parse_expression`, `parse_crontab_text`, `next_runs`,
   `describe`) so tests exercise the library, not just the CLI.
3. A parsed field is a `frozenset[int]` plus its raw text.
   Keeping the raw text lets matching decide "restricted"
   (set != full range) and lets `describe` distinguish `*`
   from an explicit full list.
4. Validation happens entirely at parse time; there is no
   half-parsed object. Any bad token raises `CronError`
   immediately, naming the field.
5. Next-run search is a minute-by-minute scan, capped at 5
   years. It is the simplest correct implementation of the
   dom/dow OR rule, including impossible dates (31 February
   simply never matches, and the cap turns that into a clear
   error instead of an infinite loop). Ordinary schedules
   resolve in at most a few thousand steps; the worst case
   (29 February) is ~2.1M steps and still completes, which the
   tests allow for but do not depend on for speed.
6. Natural-language output is deterministic and compositional
   (one phrase per field, joined in field order), not a
   hand-written sentence per pattern. Tests therefore assert
   substrings (e.g. "Saturday", "09:00"-style pieces), not
   exact prose for every exotic pattern, except for a few
   canonical cases pinned exactly.

## Module layout (single file)

- `FIELDS`: per-field (name, lo, hi, names dict) table.
- `CronError(ValueError)`: user-facing parse/validation error.
- `parse_field(text, field)` -> `frozenset[int]`: splits on
  `,`, then each item on `/` (base, step), base is `*`, a
  range `a-b`, or a single value; names resolved before the
  numeric checks so `MON-FRI` and `JAN-MAR` work, and so a
  name in a range endpoint is validated by the same code path.
- `parse_expression(text)` -> `CronExpression`: handles
  `@special` (expanding to a five-field expression, or the
  reboot marker) and five-field schedules. Splits on any
  whitespace; a trailing command (6th+ tokens) is kept as
  `command` on the expression/job, not parsed as fields.
- `CronExpression.matches(dt)`: minute/hour/month equality
  plus the dom/dow rule above; `dt` is truncated to the minute.
- `next_runs(expr, from_dt, count)`: scan described above.
- `describe(expr)` -> `str`: per-field phrases (see below).
- `parse_crontab_text(text)` -> `(jobs, errors)`: skips
  blanks/comments/env lines, parses the rest, collects
  `(lineno, line, error)` triples instead of raising.
- CLI (`main`): subcommands `explain`, `validate`, `next`,
  `matches`, `list`, plus a bare-expression shorthand
  (`crontab.py "0 9 * * 6 cmd"` == `explain`). `--from`
  and `--at` accept `YYYY-MM-DDTHH:MM` (seconds allowed and
  ignored for matching). Exit 0 on success, 1 on usage error,
  2 on a cron parse error, matching the "informative error"
  requirement without overloading one code.

## describe() phrases

- minute: `every minute` / `every N minutes` / `at minute M`
  / `at minutes A, B and C` (lists joined with commas and a
  final "and"; ranges as `minutes A through B`).
- hour: `every hour` / `every N hours` / `at HH:00`
  (zero-padded, so `0 9 * * 6` describes as "at 09:00").
- day of month: `every day` / `on day D` / `on days …`.
- month: `every month` / `in January` / `in January and March`.
- day of week: `every day of the week` is omitted when the
  day-of-month already says "every day" — instead the sentence
  is assembled as: "At <minute>, <hour>[, on <dom>][, in
  <month>][, on <dow>]." plus the special all-`*` sentence
  "At every minute, of every hour, every day."
- `@reboot` describes as "On system reboot." and `@hourly`
  etc. describe via their expanded five-field form.

## What was deliberately not built

- No `L`/`W`/`#`/`?` handling (see SPEC.md): adding a partial
  version (e.g. `L` only for dom) would mislead more than
  rejecting cleanly.
- No cron daemon / scheduler loop: the page asks for a decoder,
  and running commands on a timer would need the real crontab
  the brief forbids touching.
- No config file, no colours, no interactive UI: the page's
  Step 1 UI is a React example; this build is a CLI, which is
  the form the rest of this repo uses, and a CLI is fully
  testable without a browser.
