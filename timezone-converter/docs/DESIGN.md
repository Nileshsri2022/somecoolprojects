# DESIGN — Time Zone Converter

## Stack

- Python 3 (stdlib only): `argparse`, `datetime`, `zoneinfo`.
- One main file: `timezone_converter.py` (CLI + library functions in
  one module so tests import it directly; no package scaffolding).
- Tests: `tests/test_timezone_converter.py`, stdlib `unittest` only.

## Module layout

| Function | Role |
|----------|------|
| `ABBREVIATIONS` | Small explicit abbreviation → IANA map (see SPEC §Divergences). |
| `resolve_zone(name)` | Abbreviation → IANA; else exact IANA; else unique city substring; else `ValueError` (ambiguous matches listed, unknown names get usage hint). |
| `load_zone(name)` | `resolve_zone` + `ZoneInfo`, converting a missing tz database entry into a `pip install tzdata` hint. |
| `parse_time(text, tz)` | `now`, bare `HH:MM[:SS]` (today in source zone), or full datetime; raises `ValueError` on garbage. |
| `fmt_offset(dt)` / `fmt_dt(dt)` | `+HH:MM` offsets and `YYYY-MM-DD HH:MM ±HH:MM (ABBR)` rendering. `tzname()` supplies the abbreviation actually in effect (e.g. BST vs GMT), so output never claims a fixed abbreviation. |
| `convert(src_dt, targets)` | Ordered conversion; argument order preserved (Step 2 re-ordering). |
| `sort_relative(src_dt, targets)` | Sort key `(offset − source offset, name)` — negative offsets first (Step 2). |
| `day_table(first, rest, date)` | 24 rows, hours 0–23 of the first zone, each row one instant rendered in every zone (Step 3). Uses `fold=0` throughout; see SPEC for gap-day behaviour. |
| `window(ref, start, end, targets)` | Start/end pair per zone; end ≤ start rolls to next day (Step 4). |
| `list_zones(query)` | Sorted IANA list, optional substring filter. |
| `main(argv)` | `argparse` subcommands `convert`, `sort`, `table`, `window`, `list`. All `ValueError`s become `error: ...` on stderr with exit code 2; `argparse` errors keep their standard exit code 2. |

## Key decisions

- **zoneinfo, not fixed offsets.** Every conversion goes through
  `astimezone()` on a real IANA zone, so DST transitions, half-hour
  zones (Kolkata +05:30, Adelaide +10:30/+11:00), and southern-
  hemisphere reversed DST fall out of the database, not hand tables.
- **Abbreviation-first resolution.** Deliberate (SPEC divergence 2):
  a user typing `EST` means US Eastern, not the tzdb fixed-offset
  `EST` zone. The cost — the fixed `EST` zone is unreachable by that
  spelling — is documented and acceptable.
- **Bare times anchor to the source zone's today, not UTC's today.**
  `parse_time("09:30", tz)` uses `datetime.now(tz).date()`, so a bare
  time near midnight converts with the correct side of the date line.
- **No state, no I/O beyond stdout/stderr.** No config file, no
  cache, no network. The only external dependency is the tz database.
- **Errors are loud.** Unknown/ambiguous zones and unparsable times
  fail with exit code 2 and a message naming the bad value, instead
  of silently falling back to UTC.

## CLI surface

```
convert --from ZONE --time TIME --to ZONE [ZONE ...]
sort    --from ZONE [--time TIME] --to ZONE [ZONE ...]
table   --zones ZONE [ZONE ...] [--date YYYY-MM-DD]
window  --from ZONE [--time TIME] --start HH:MM --end HH:MM --to ZONE [ZONE ...]
list    [QUERY] | list --abbreviations
```
