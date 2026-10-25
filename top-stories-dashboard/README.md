# Top Programming Stories Dashboard — Build Your Own Top Programming Stories Dashboard

Coding Challenges "Build Your Own Top Programming Stories Dashboard"
(https://codingchallenges.fyi/challenges/challenge-top-stories),
worked in `somecoolprojects/`. Docs first, then code — see `docs/`.

Distinct from the already-built `top` project (a `/proc` process
monitor): the only shared word is "Top". Different domain, different
data source, different program.

A Hacker News dashboard in Python 3, standard library only: a scraper
for the public HN API (no key), a producer polling every 60 seconds,
a backend API with in-memory store and configurable consumer-side
filtering, and a web frontend with auto-refresh.

## Usage

```sh
# Step 1: fetch once, print as JSON lines
python3 top_stories.py scrape --limit 10

# Step 2: poll HN and append new stories to the hn-stories topic log
python3 top_stories.py produce --once
python3 top_stories.py produce            # polls every 60 s until Ctrl-C

# Steps 3-4: serve the API + frontend (default port 8000)
python3 top_stories.py serve
python3 top_stories.py serve --config config.yaml --port 8000
```

Then open http://127.0.0.1:8000/ — the frontend re-fetches every
30 seconds. API endpoints:

- `GET /stories` — stored stories, newest first
- `GET /stories/top` — sorted by score, descending
- Query filters on both: `?min_score=N`, `?keyword=WORD`,
  `?source=hackernews`, `?since=UNIXSECONDS`, `?limit=N`

## Config (Step 4)

`config.yaml` controls which stories an instance keeps. Example:

```yaml
min_score: 50
keywords:
  - rust
sources:
  - hackernews
max_age_hours: 48
```

All keys optional; absent = accept all. Run the same server with a
different `--config` for different instances (high-score, keyword,
etc.). Only the small YAML subset above is parsed — unknown keys and
non-integer scores are errors, not silently ignored.

## Deliberate divergence: no real Kafka

The challenge suggests a free Aiven Kafka cluster and a topic called
`hn-stories`. No Kafka/Aiven account was created and no credentials
were invented for this build. The topic is a local JSON-lines file
(default `hn-stories.jsonl`); each line is one JSON story message,
the format a Kafka producer would carry. The producer deduplicates by
story `id`, the backend re-reads the log into memory on each request
(so a running producer's stories appear without restarting the
server). Swapping in a real Kafka producer/consumer later means
replacing the log read/append functions; story format, poll loop,
dedup and filtering stay the same.

## Not built

- **Reddit multi-source aggregation (Going Further):** not built.
  Reddit's unauthenticated JSON endpoint is not a reliable public API
  like HN's, so a Reddit scraper here could not be verified
  headlessly and would risk being fake capability. Every story already
  carries a `source` field and the API already supports `?source=`
  filtering, so a verified Reddit source can plug in later.
- No authentication, rate limiting, or HTTPS: local use only.
- The in-memory store is rebuilt from the log per request; there is
  no streaming consumer thread and no persistence beyond the log file.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

16 tests, all passing. Tests use a fake HN server on an ephemeral
port — no live network. Live HN fetching, the 60 s loop timing,
browser rendering, real Kafka, and Reddit are not claimed as tested;
see `docs/TEST_PLAN.md`.
