# Time Zone Converter

CLI tool to convert times between time zones, built for Coding
Challenge #85 — "Build Your Own Time Zone Converter"
(<http://codingchallenges.fyi/challenges/timezone-converter/>).

Python 3 standard library only. DST is handled by the IANA timezone
database via `zoneinfo` — offsets are computed for the actual date
being converted, never from a fixed abbreviation offset.

## Usage

```bash
# Convert one time to several zones (Step 1)
python3 timezone_converter.py convert \
  --from Europe/London --time "2026-03-29 09:30" \
  --to America/New_York America/Los_Angeles Asia/Kolkata

# Sort zones relative to the source: negative offsets first (Step 2)
python3 timezone_converter.py sort \
  --from Europe/London --time "2026-03-29 09:30" \
  --to America/New_York Asia/Kolkata

# 24-hour table, aligned, starting 0:00 in the first zone (Step 3)
python3 timezone_converter.py table \
  --zones Europe/London America/New_York --date 2026-03-29

# Highlight a period: start and end in every zone (Step 4)
python3 timezone_converter.py window \
  --from Europe/London --time "2026-03-29 09:00" \
  --start 09:00 --end 10:30 --to America/New_York Asia/Kolkata

# Find zones / see the abbreviation mapping
python3 timezone_converter.py list london
python3 timezone_converter.py list --abbreviations
```

Zones accept IANA names (`Europe/London`), city names (`london`,
`new_york`), or abbreviations (`CET`, `EST`, `PST`). Times accept
`HH:MM`, `YYYY-MM-DD HH:MM`, ISO `T` form, optional seconds, or
`now`.

## DST handling

- US DST starts 2026-03-08, Europe 2026-03-29: on 2026-03-15 London is
  still GMT while New York is already EDT — the converter gets this
  right because offsets come from the IANA rules for the date.
- On a spring-forward day the skipped wall hour maps (fold=0) onto
  the previous instant; the 24-row table still has 24 rows. On a
  fall-back day a bare wall time means the first occurrence.
- Abbreviations map to DST-observing zones: `EST` in July converts as
  EDT (−04:00). Ambiguous abbreviations resolve to one documented
  reading: `IST` → `Asia/Kolkata`, `CST` → `America/Chicago`,
  `GMT` → `Europe/London`. Prefer IANA names for exactness.

## If the timezone database is missing

`zoneinfo` needs the system tz database. If it is absent you get a
clear error telling you to install system tzdata or run
`pip install tzdata`.

## Tests

```bash
python3 -m unittest discover -s tests -v   # 22 tests
```

## Scope limits

CLI only — no GUI, web UI, live clock, or interactive drag/reorder
(the challenge's Step 0 explicitly allows a CLI; hover becomes table
rows, dragging becomes `--start`/`--end`, re-ordering becomes
argument order). No meeting-slot finder and no `--fold` flag for the
second occurrence of a repeated hour. See `docs/SPEC.md` for the full
step-by-step mapping, divergences, and everything not built.
