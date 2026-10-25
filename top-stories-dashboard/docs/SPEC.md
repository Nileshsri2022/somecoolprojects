# SPEC — Top Programming Stories Dashboard

Source challenge: "Build Your Own Top Programming Stories Dashboard"
(https://codingchallenges.fyi/challenges/challenge-top-stories), re-read
2026-10-26 before any code was written. This spec is that page's steps,
not an invention: where this build differs, the difference is stated
below and in README.md, never silently.

Distinct from the already-built `top` project in `somecoolprojects/top/`
(a `/proc` process monitor): the only shared word is "Top". Nothing is
reused from it; different domain, different data source, different
program.

## Step Zero — environment

Python 3 standard library only. No third-party packages, no Kafka
client library, no `curl`/`Postman` dependency (the API is tested with
Python's own `urllib` and the bundled unittest suite). Project layout:

```
top-stories-dashboard/
  README.md
  top_stories.py        # the whole program: scraper, producer, API, consumer filter
  config.yaml           # consumer-side filtering (Step 4)
  frontend/index.html   # Step 5 frontend (static, served by the backend)
  docs/SPEC.md, DESIGN.md, TEST_PLAN.md
  tests/test_top_stories.py
```

## Step 1 — Hacker News scraper

Public Hacker News API, no key: base `https://hacker-news.firebaseio.com/v0/`.

- `GET <base>/topstories.json` and `<base>/newstories.json` return
  arrays of story IDs.
- `GET <base>/item/<id>.json` returns one item, e.g.
  `{"by": "username", "id": 12345, "score": 142, "time": 1234567890,
    "title": "Something interesting", "type": "story",
    "url": "https://example.com"}`.
- A story object in this program has: `id`, `title`, `url`, `score`,
  `by` (author), `time` (unix seconds), `type`, plus `source`
  (`"hackernews"`) and `feed` (`"top"` or `"new"`, recording which list
  it came from).
- Only items with `type == "story"` are kept; jobs, comments, polls
  and dead/deleted items are skipped. Items missing a title are kept
  with an empty title only if they are stories (the API normally
  supplies one); missing `url` becomes `""`, missing `score` becomes
  `0`, missing `time` becomes `0`. Nothing is invented for a missing
  field beyond those neutral defaults.
- `scrape` subcommand prints stories to stdout as JSON lines, for
  console verification exactly as the challenge suggests.

## Step 2 — producer, `hn-stories` topic, 60 s poll

The challenge asks for an Aiven free Kafka cluster and a topic called
`hn-stories`, with the scraper publishing each story as a JSON message
and polling every 60 seconds.

### Deliberate divergence (documented, not hidden)

No Kafka/Aiven account was created and no credentials were invented
for this build (per the build brief: account dependencies are out of
scope). The topic is therefore a **local append-log standing in for
the Kafka topic**: a JSON-lines file (default `hn-stories.jsonl`) in
which each line is one JSON story message — the same message format
the Kafka version would carry. The producer appends only stories not
already in the log (deduplicated by story `id`), polls every 60
seconds by default (`--poll-interval`, `--once` for a single pass),
and logs errors to stderr and keeps polling when the HN API or the
log is temporarily unavailable, instead of crashing. Swapping the log
for a real Kafka producer later means replacing `append_to_log` /
`read_log` with produce/consume calls; the story format, the poll
loop, the dedup rule and the consumer filter do not change.

## Step 3 — backend API consuming the topic, in-memory store

The backend reads the topic log into an in-memory store (a dict keyed
by story `id`, latest copy wins) and serves:

- `GET /stories` — all stored stories, newest first by default.
- `GET /stories/top` — stories sorted by score descending.
- Query filters on both: `?min_score=N`, `?keyword=WORD`
  (case-insensitive substring of the title), `?source=hackernews`,
  `?since=UNIXSECONDS` (stories with `time >= since`), `?limit=N`.
- `GET /` and `GET /index.html` — the Step 5 frontend.
- Anything else: HTTP 404 with a JSON `{"error": ...}` body.
- The store is re-read from the log file on every API request, so a
  running `produce` loop's new stories appear in the API without
  restarting the server, and without a background consumer thread.
  This is a deliberate simplification of "consume from Kafka": the
  file is re-read, not streamed, and the store is in-memory only —
  restarting the server with an empty log serves an empty list.

## Step 4 — configurable consumer-side filtering (`config.yaml`)

`config.yaml` (in the project directory, overridable with
`--config`) controls which stories an API instance stores/serves.
Supported keys (all optional; absent keys mean "accept all"):

```yaml
min_score: 50
keywords:
  - rust
  - python
sources:
  - hackernews
max_age_hours: 48
```

Semantics: a story is kept only if `score >= min_score` AND
(title contains any keyword, when keywords are non-empty) AND
(`source` is in `sources`, when sources are non-empty) AND
(`time` is within `max_age_hours` of now, when set). Filtering is
applied at ingest/read time, so separate instances with different
`config.yaml` files (e.g. an Ask-HN-style instance, a Rust-keyword
instance, a high-score instance) each serve only their subset while
exposing the same `/stories` API. The challenge's Step 4 examples
(`story-api-ask`, `story-api-rust`, `story-api-top`) are instance
configurations, not separate programs: run the same server with a
different `--config`.

Note on YAML parsing: Python's standard library has no YAML parser,
so this program parses only the small subset above (comments,
`key: scalar`, `key:` followed by `- item` lines, and inline
`[a, b]` lists). Anything outside that subset is an error, not
silently ignored — see DESIGN.md. A real deployment would use a YAML
library; the subset is stated here so nobody mistakes it for full
YAML.

## Step 5 — web frontend with auto-refresh

`frontend/index.html` is plain HTML + JavaScript (no framework, no
build step). It fetches `/stories/top`, renders title (linked to the
story URL when present), score, author and time, and re-fetches every
30 seconds without a page reload, plus a manual Refresh button and a
score filter box that re-queries `?min_score=`. It is served by the
backend itself (`GET /`), so there is no second server to run.

## Going Further — Reddit multi-source aggregation: NOT BUILT

The challenge's Going Further asks for Reddit support (r/programming,
r/technology via Reddit's JSON API), a separate topic or a `source`
field, merged consumption, and source filtering. **This is not built
in this version.** Reason: Reddit's unauthenticated JSON endpoint is
not a reliable public API in the way HN's is (it increasingly
requires OAuth / authenticated access), so a Reddit scraper written
here could not be verified headlessly and would risk being fake
capability. It is recorded as not built rather than stubbed. What IS
in place for it: every story already carries a `source` field, and
the API already supports `?source=` filtering, so adding a verified
Reddit source later is a producer addition, not an API redesign.

## Limits (honest, complete)

- No real Kafka, no Aiven cluster, no Kafka client: the topic is a
  local JSON-lines file (see Step 2 divergence).
- No persistence beyond the log file; the in-memory store is rebuilt
  from the log on each request.
- No authentication, no rate limiting, no HTTPS: local use only.
- The YAML parser covers only the `config.yaml` subset above.
- Frontend auto-refresh is a 30 s poll, not a push/WebSocket feed.
- Reddit aggregation is not built (see above).
- Live HN fetching is not part of the automated tests (tests use a
  fake HN server on an ephemeral port); a live run needs network
  access to `hacker-news.firebaseio.com`.
