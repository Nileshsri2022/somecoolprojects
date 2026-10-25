# DESIGN — Top Programming Stories Dashboard

One program, Python 3 standard library only: `top_stories.py`.
No frameworks (no Flask/FastAPI), no third-party packages. The HTTP
server is `http.server.ThreadingHTTPServer`; HTTP client work is
`urllib.request`; JSON is `json`; config parsing is hand-written for
the documented subset (see SPEC.md Step 4).

## Modules inside the single file

| Area | Functions / classes |
|---|---|
| HN client | `fetch_json(url)`, `fetch_story_ids(base, feed)`, `fetch_story(base, id)`, `fetch_feed(base, feed, limit)` |
| Story model | plain `dict`s, normalised by `normalise_story(raw, feed)` — never a bare pass-through of API JSON, so unknown fields cannot leak into the log and missing fields get neutral defaults |
| Topic log (Kafka stand-in) | `append_to_log(path, stories)` (dedups by `id` against the existing log), `read_log(path)` (dict keyed by `id`, latest wins) |
| Filtering | `parse_config(text)` / `load_config(path)`, `story_matches(story, config)`, `apply_query_filters(stories, params)` |
| API server | `make_handler(log_path, config, frontend_path)` returning a `BaseHTTPRequestHandler` subclass; `serve(...)` |
| CLI | `argparse` subcommands `scrape`, `produce`, `serve`; `main(argv)` returns an exit code |

## Data flow

```
HN API --fetch_feed--> stories --append_to_log--> hn-stories.jsonl
                                                        |
API request --> read_log --> story_matches(config) -----> in-memory dict
                     --> apply_query_filters(params) --> JSON response
                     \-> frontend/index.html served for GET /
```

`produce` loop: fetch top + new feeds, merge, append new stories,
sleep `--poll-interval` (default 60), repeat; on a fetch error, print
to stderr and continue at the next interval. `--once` performs exactly
one pass (this is what tests and one-shot runs use).

`serve` loop: no consumer thread. Each `/stories*` request re-reads
the log, applies the instance config, then the query filters. Cost is
one file read per request; acceptable for a local dashboard, and it
keeps "new stories appear" true without any background state. If the
log file does not exist yet, the API serves `[]` rather than erroring.

## Filtering order

1. Config filter (Step 4, instance-level, at read time).
2. Query filter (Step 3, per-request): `min_score`, `keyword`,
   `source`, `since`, `limit`, in that order; sorting is applied by
   endpoint (`/stories`: `time` desc; `/stories/top`: `score` desc,
   ties broken by `time` desc).

## Config subset parser

`parse_config` accepts, per line: blank lines, `#` comments,
`key: value` (integer for `min_score`/`max_age_hours`, string
otherwise), `key:` followed by indented `- item` lines, and
`key: [a, b]` inline lists. Unknown keys raise `ValueError`; a
non-integer where an integer is required raises `ValueError`. This
fail-loud rule is deliberate: a typo'd config must not silently
become "accept everything".

Defaults when no config file exists (serve without `--config`):
`min_score 0`, no keywords, no source restriction, no age limit —
i.e. serve everything in the log.

## Frontend

`frontend/index.html` contains no build step and no external
dependencies (no CDN scripts). `fetch('/stories/top?min_score=...')`,
render, `setInterval(..., 30000)`. Story time is rendered from the
unix timestamp with `Date` in the browser's local timezone; a story
with `time == 0` renders as "unknown time".

## Error handling

- HN fetch failure (non-200, timeout, bad JSON): `fetch_json` raises;
  `scrape` exits non-zero with the error on stderr; `produce` logs
  and retries next interval.
- Malformed lines in the log file are skipped (with a stderr warning
  on read), never fatal — one corrupt line must not kill the API.
- Bad query values (`min_score=abc`): that filter is ignored and the
  request still succeeds; bad config values are fatal at startup
  instead, because a config is an operator decision, not user input.
