# SPEC — CronTab Tool

Source: Coding Challenges, "Build Your Own Crontab Tool".
Page slug used: `challenge-cron`
(URL: https://codingchallenges.fyi/challenges/challenge-cron)

Slug correction: the first guess `challenge-crontab` returned HTTP 404.
The tag page for "unix" links "Build Your Own Crontab Tool" to
`challenge-cron`; that page loads and is the spec source below.

## What the page asks for

- Step 1: accept a cron expression of five fields, e.g. `0 9 * * SAT`.
- Step 2: validate the expression and give an informative error
  when it is not valid (the page suggests TDD with valid/invalid
  patterns).
- Step 3: translate the expression into natural language, e.g.
  the page's newsletter example `0 9 * * 6 <command>` = 9am on
  Saturdays.

Field table from the page:

| Field        | Allowed values      | Special chars |
|--------------|---------------------|---------------|
| minute       | 0–59                | `* , - /`     |
| hour         | 0–23                | `* , - /`     |
| day of month | 1–31                | `* , - /` (+ `? L W` only in some implementations) |
| month        | 1–12 or JAN–DEC     | `* , - /`     |
| day of week  | 0–6 or SUN–SAT      | `* , - /` (+ `? L #` only in some implementations) |

The page also mentions extensions `@yearly`, `@monthly`, `@daily`
"and so on". The standard set is supported here:
`@yearly`/`@annually`, `@monthly`, `@weekly`, `@daily`/`@midnight`,
`@hourly`, `@reboot`.

## What this build adds (beyond the page, per the task brief)

The page's tool is a decoder (validate + explain). This build also
provides, because a decoder that cannot answer "when does it run?"
is of limited use, and the brief asks for them:

- `next_runs`: the next N run times after a given moment.
- `matches`: whether an expression matches a given datetime.
- Crontab-file parsing (`list`): blank lines, `#` comments and
  `NAME=value` environment lines are skipped; each remaining line
  is five fields plus a command (the command may contain spaces).
  Invalid lines are reported, not silently dropped.

## Behaviour contract

- Input: five whitespace-separated fields, or one `@special`
  token followed by a command. A schedule alone (no command) is
  valid for `explain`/`validate`/`next`; a command is optional.
- Names are case-insensitive; full names (`JANUARY`, `SATURDAY`)
  and 3-letter abbreviations (`JAN`, `SAT`) are accepted.
- Day of week: 0 and 7 both mean Sunday (7 is normalised to 0,
  as the page notes "7 is Sunday on some systems").
- Steps: `*/n`, `a-b/n`, `a/n` (meaning `a` to the field maximum,
  stepping by `n`). Step must be a positive integer.
- Lists may mix values, ranges and steps: `1,15,30-45/5`.
- Matching (Vixie-cron semantics): minute, hour and month must
  match. Day-of-month / day-of-week: if both fields are
  restricted (their expanded set is not the full range) the job
  runs when EITHER matches; if only one is restricted, only it
  decides; if neither is restricted, every day matches. A field
  expanding to the full range (e.g. `*/1`) counts as unrestricted.
- `next_runs` is strictly after the given moment (a job scheduled
  exactly at that moment is not returned). Seconds/microseconds
  of the reference moment are ignored beyond pushing to the next
  minute boundary.
- Errors: a single `CronError` naming the offending field and the
  reason, e.g. `minute: value 60 out of range 0-59`. The CLI
  prints `crontab: <error>` and exits non-zero. No error message
  is ever a bare traceback for bad user input.
- Nothing in this tool installs, edits or reads the real system
  crontab. It only reads files explicitly named on the command
  line (or stdin for `list -`). Tests use only temp files.

## Out of scope (documented divergences)

- `?`, `L`, `W`, `#` (nth weekday): the page itself says these
  exist "only in some implementations". They are rejected with
  an informative error, not silently misinterpreted.
- `@reboot` has no schedule: it parses and describes as
  "on system reboot", but `next_runs` refuses it (no run time
  can be computed) instead of inventing one.
- Seconds / year fields (Quartz-style) are not supported: the
  page defines five fields. Tokens after the five fields are
  the command, as in standard crontab — so a six-token line
  is five fields plus a command, not a seconds field.
- No job execution, no daemon, no writing to the system crontab.
- Timezones/DST: all datetimes are naive local datetimes, as
  system cron treats wall-clock time. DST gaps/repeats are not
  special-cased (same as Vixie cron's minute-granularity view
  for ordinary schedules).
