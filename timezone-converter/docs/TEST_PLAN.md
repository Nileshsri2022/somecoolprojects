# TEST_PLAN — Time Zone Converter

## How to run

```
cd timezone-converter
python3 -m unittest discover -s tests -v
```

Stdlib only; no network, no fixtures, no tzdata download (uses the
system database; the suite fails loudly if it is absent, which is
itself the documented behaviour).

## Coverage (22 tests, all passing at delivery)

| Area | Tests | What is pinned |
|------|-------|----------------|
| Zone resolution | 5 | IANA passthrough; abbreviations (CET/EST/PST, case-insensitive); city substring (`london`, `kolkata`); unknown zone raises; ambiguous substring raises instead of guessing. |
| Basic conversion | 4 | Winter London→New York/Kolkata; summer offsets (EDT −04:00); date rollover LA→Tokyo (+1 day); half-hour zones (Kolkata +05:30, Adelaide +10:30 in Jan DST). |
| DST | 5 | London spring-forward 2026-03-29 (GMT→BST); US/Europe March divergence (2026-03-15: London GMT, New York EDT); US fall-back 2026-11-01 repeated hour, fold 0 vs 1 differ by exactly 1 h in UTC; Sydney reversed DST (+11 Jan / +10 Jul); Tokyo no-DST control. |
| Time parsing | 2 | All documented formats incl. `T` separator and seconds; bare `HH:MM` anchors to source zone; garbage raises. |
| Sort + window | 3 | Negative-offset zone sorts before positive; window start/end per zone (London 09:00–10:30 → New York 04:00–05:30); window crossing midnight rolls end to next day. |
| 24-hour table | 2 | 24 rows, first column 00:00–23:00 of first zone, New York column correct (19:00 previous day at row 0); spring-forward day still 24 rows with the skipped hour collapsing onto the previous instant (fold=0). |
| Mapping guard | 1 | `IST` → `Asia/Kolkata` pinned, so the ambiguous mapping cannot drift silently. |

## Manual checks performed (in addition to the suite)

- `convert --from Europe/London --time "2026-03-29 09:30" --to
  America/New_York America/Los_Angeles Asia/Kolkata CET` → BST/EDT/
  PDT/IST/CEST all correct.
- `sort` output orders New York (−05:00 rel.) before Kolkata (+04:30).
- `table --zones Europe/London America/New_York --date 2026-03-29`
  shows the GMT→BST switch between rows 1 and 2.
- `list london` → `Europe/London`; unknown zone exits 2 with a
  helpful error; `EST` in July converts as EDT (−04:00) via New York.
- Three test failures during development caught real issues (see
  below) and were fixed, not skipped.

## Failures found and fixed during development

1. `EST`/`CET` initially resolved to the tzdb fixed zones of the same
   name instead of the abbreviation map — fixed by making abbreviation
   lookup run before the exact-IANA check (SPEC divergence 2).
2. Two test assertions (not code) were wrong about `fold` semantics:
   aware subtraction with the same tzinfo ignores fold, and a gap
   hour's `utcoffset()` differs from its UTC instant — both tests now
   compare via UTC. No production code was changed for these two.

## Not covered (stated limits)

- No test for a missing system tz database (would require removing
  the database from the test machine); the error path is code-
  reviewed and its message is in SPEC.
- No CLI end-to-end subprocess tests; the suite tests the same
  functions `main()` calls, and the commands above were run manually.
- `fold=1` (second occurrence of a repeated hour) is not reachable
  from the CLI and is tested only at the `zoneinfo` level.
