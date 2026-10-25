# crontab — Build Your Own Crontab Tool

Coding Challenges #32, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.
Page: https://codingchallenges.fyi/challenges/challenge-cron
(slug `challenge-cron`; `challenge-crontab` 404s).

Decodes, validates and explains cron expressions, and answers
"when does it run?" — next runs, matching, and crontab-file
listing. Python 3 standard library only, single file
`crontab.py`. Nothing here installs, edits or reads the real
system crontab.

## Usage

```sh
python3 crontab.py "0 9 * * 6 send-newsletter"
python3 crontab.py explain "0 9 * * SAT"
python3 crontab.py validate "61 * * * *"
python3 crontab.py next "*/15 * * * *" --from 2026-10-25T10:07 --count 3
python3 crontab.py matches "0 9 * * 6" --at 2026-10-31T09:00
python3 crontab.py list jobs.txt --at 2026-10-31T09:00 --next 1
cat jobs.txt | python3 crontab.py list -
```

- Five fields: minute (0–59), hour (0–23), day of month
  (1–31), month (1–12 or JAN–DEC), day of week (0–6 or
  SUN–SAT, 7 also means Sunday). Lists (`,`), ranges (`-`)
  and steps (`/`) may be mixed: `1,15,30-45/5`.
- `@yearly`, `@annually`, `@monthly`, `@weekly`, `@daily`,
  `@midnight`, `@hourly`, `@reboot` are supported.
- Matching follows Vixie cron: minute/hour/month must match;
  if both day-of-month and day-of-week are restricted, either
  matching is enough; if only one is restricted, it decides.
- `next` is strictly after the reference moment. `validate`
  exits 2 with a message naming the offending field.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use only in-memory strings and temp files; they never
invoke the system `crontab` binary.

## Deliberate divergences

- `?`, `L`, `W`, `#` are rejected, not half-implemented: the
  page itself says they exist "only in some implementations".
- `@reboot` parses and describes, but has no next run —
  inventing one would be wrong.
- No seconds/year field, no job execution, no daemon: the
  page asks for a decoder, and the brief forbids touching
  the real crontab.
- Datetimes are naive local times; DST gaps/repeats are not
  special-cased.
