# TEST_PLAN — Top Programming Stories Dashboard

Suite: `tests/test_top_stories.py`, run with
`python3 -m unittest discover -s tests -v` from the project directory.
Standard library `unittest` only. No live network: every network test
uses a fake Hacker News server (or a real API server under test) bound
to an ephemeral port (`port=0`), shut down in `tearDown`. No test
server is left running after the suite.

## Fake HN server

A `ThreadingHTTPServer` whose handler serves, from in-memory fixtures:

- `/v0/topstories.json` → `[1, 2, 3]`
- `/v0/newstories.json` → `[3, 4]`
- `/v0/item/1.json` → a normal story (score 142)
- `/v0/item/2.json` → a story with no `url`
- `/v0/item/3.json` → a `type: "job"` item (must be skipped)
- `/v0/item/4.json` → a low-score story (score 5)
- anything else → 404

## Cases

Scraper:
- `fetch_story_ids` returns the fixture ID lists for `top` and `new`.
- `fetch_story` normalises a normal story (all fields, `source ==
  "hackernews"`, `feed` recorded).
- `fetch_feed` skips non-story items, keeps a story missing `url`
  with `url == ""`, and honours `limit`.

Config:
- `parse_config` parses scalar, block-list and inline-list forms,
  ignores comments/blank lines, and defaults missing keys.
- `parse_config` raises `ValueError` on an unknown key and on a
  non-integer `min_score`.
- `story_matches` enforces `min_score`, keyword (case-insensitive,
  any-of), `sources`, and `max_age_hours` (with a fixed "now" via a
  monkeypatched time source — implemented by passing `now` explicitly).

Topic log:
- `append_to_log` writes JSON lines, appends only new IDs on a
  second call, and `read_log` returns the latest copy per ID.
- `read_log` skips a corrupt line instead of raising, and returns
  `[]` for a missing file.

API (real server under test, ephemeral port, temp log + temp config):
- `GET /stories` returns config-filtered stories, newest first.
- `GET /stories/top` returns them score-descending.
- `?min_score=`, `?keyword=`, `?source=`, `?since=`, `?limit=`
  each narrow the result as specified.
- `GET /` returns HTML containing the dashboard title.
- Unknown path returns 404 with a JSON error body.

## What is NOT claimed as tested

- Live fetching from `hacker-news.firebaseio.com` (needs real
  network; the fake server proves the parsing, not the live service).
- The 60 s `produce` loop timing (only `--once` behaviour is tested;
  a 60 s sleep is not waited out in the suite).
- Browser rendering of the frontend (only that the server returns
  the HTML; JS execution is not headlessly asserted).
- Real Kafka / Aiven behaviour — there is none in this build.
- Reddit aggregation — not built.
