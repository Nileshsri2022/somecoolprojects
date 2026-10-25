# SPEC — Time Zone Converter

## Challenge

- Source: Coding Challenges, "Build Your Own Time Zone Converter"
  (Coding Challenge #85).
- Resolved page URL (read before writing any code):
  <http://codingchallenges.fyi/challenges/timezone-converter/>
  (mirror: <https://codingchallenges.substack.com/p/coding-challenge-85-time-zone-converter>).
  Found via the site's tag index
  (<https://codingchallenges.fyi/challenges/tags>) plus web search;
  the first search hit was the fyi page itself.
- Goal (page wording, paraphrased): a tool to visualise and plan
  meetings across multiple time zones — enter a source timezone and
  one or more additional timezones, see the time in each relative to
  the source, accounting for daylight saving time changes around the
  world (which happen on different dates in different countries).

## Challenge steps and how each is implemented

| Step | Page requirement | Implementation in this project |
|------|------------------|-------------------------------|
| 0 | Choose a stack; frontend / GUI / CLI are all acceptable | CLI, Python 3 stdlib only (see DESIGN.md). No GUI, no web server, no live clock service — per the Wave 3 triage. |
| 1 | Enter a source timezone and one or more additional timezones; ideally pick by city or timezone abbreviation | `convert --from <zone> --time <time> --to <zones...>`; zones accept IANA names (`Europe/London`), city substrings (`london`, `new_york`), or abbreviations (`CET`, `EST`). `list [query]` and `list --abbreviations` show available zones and the abbreviation mapping. |
| 2 | Display the zones in a list; allow re-ordering; sort relative to the source so negative-offset zones come before the source and positive-offset zones after it | `sort --from <zone> --time <time> --to <zones...>` prints zones ordered by (offset − source offset, name). Re-ordering is by argument order in `convert`/`table` (the first zone anchors the table); there is no interactive drag-to-reorder in a CLI — see Divergences. |
| 3 | Show 24 hours of each timezone, aligned, starting from 0:00 in the first listed timezone; hover over an hour to see the group of times that apply at that time | `table --zones <first> <rest...> [--date YYYY-MM-DD]` prints 24 rows (hours 0–23 of the first zone), each column being that same instant in another zone. Hover has no CLI equivalent; each printed row IS the "group of times that apply at that hour". |
| 4 | Highlight a time period and show it as start and end time for each timezone (drag the green bar) | `window --from <zone> [--time <ref>] --start HH:MM --end HH:MM --to <zones...>` prints the period's start and end in every zone. Dragging is replaced by explicit `--start`/`--end`; an end earlier than the start is read as next-day. |
| 5 | Reflect daylight saving time, in March and October/November | All offsets come from `zoneinfo` IANA rules for the actual date converted — never from a fixed abbreviation offset. Covered by tests for London spring-forward (2026-03-29), US spring-forward (2026-03-08, three weeks before Europe), US fall-back (2026-11-01), and southern-hemisphere reversed DST (Sydney). |

## Supported input formats

`--time` accepts:

- `HH:MM` or `HH:MM:SS` — today, in the source zone.
- `YYYY-MM-DD HH:MM` / `YYYY-MM-DD HH:MM:SS`
- `YYYY-MM-DDTHH:MM` / `YYYY-MM-DDTHH:MM:SS`
- `now` — the current instant (converted from UTC, so it is exact even
  across a DST boundary).

`--date` (table) is `YYYY-MM-DD`; default is today in the first zone.
`--start`/`--end` (window) are `HH:MM[:SS]` on the reference date, or
full datetimes in the formats above.

## DST handling, exactly

- Offsets are computed per date via `zoneinfo`. Example: London–New
  York is 5 hours apart in January but 4 hours apart on 2026-03-15,
  because the US is already on EDT while London is still on GMT.
- Spring-forward (gap) wall times: `zoneinfo` with `fold=0` maps the
  skipped wall hour onto the same instant as the previous hour. The
  24-row table therefore still has 24 rows on a gap day, but two rows
  share one instant (verified by test). This is stated, not hidden.
- Fall-back (repeated) wall times: input datetimes use `fold=0`
  (first occurrence). The CLI does not offer a `--fold` flag; a user
  needing the second occurrence must pass the time in UTC or in a
  non-ambiguous zone.
- Abbreviations have no DST of their own: `EST` maps to
  `America/New_York`, so `EST` in July converts as EDT (−04:00).
  This is intentional — see Divergences.

## Deliberate divergences (all documented, none silent)

1. **CLI instead of website/GUI.** The page allows a CLI explicitly
   (Step 0). Consequently: no hover, no drag, no re-order-by-mouse —
   replaced by `table` rows, `window --start/--end`, and argument
   order respectively.
2. **Abbreviations win over same-named tzdb zones.** The IANA
   database itself ships zones named `CET`, `EST`, `MST`, `HST`, etc.
   (e.g. `EST` is fixed −05:00, no DST). Resolving `EST` to that zone
   would contradict what a user means by "Eastern time" in July, so
   abbreviation lookup runs before the exact-IANA check. Users who
   want a fixed-offset zone should use `Etc/GMT+5` or an explicit
   `UTC±` offset zone instead.
3. **Ambiguous abbreviations resolve to one documented reading.**
   `IST` → `Asia/Kolkata` (not Israel Standard Time or Irish Standard
   Time); `CST` → `America/Chicago` (not China Standard Time);
   `GMT` → `Europe/London` (so "GMT" in summer behaves as BST, matching
   the challenge author's UK usage). Prefer IANA names for exactness.
   Full mapping: `list --abbreviations`.
4. **Ambiguous city substrings are rejected, not guessed.** `london`
   resolves (unique); a substring matching several zones (e.g. `a`)
   errors and lists matches.
5. **No live clock / auto-refresh.** `now` is a one-shot snapshot.
   No GUI, no server, no background process is left running.

## NOT built (honestly)

- No GUI, web UI, or live clock service.
- No interactive re-ordering (drag/drop); ordering is by CLI argument.
- No meeting-slot finder ("find a time that works for everyone") —
  the page's motivating example, but not one of its numbered steps.
- No `--fold` flag for the second occurrence of a repeated hour.
- No non-IANA zone support beyond the documented abbreviation map
  (no custom `UTC+05:30` free-form offsets; `Etc/GMT±N` IANA names
  work, noting their inverted sign convention).

## System tz database

Conversion uses Python's stdlib `zoneinfo`. If the system tz database
is absent, the program errors with a clear message directing the user
to install system tzdata or `pip install tzdata` (which `zoneinfo`
picks up automatically). No third-party package is required when the
system database is present (verified in this environment: Python
3.12.3, system tzdata present).
