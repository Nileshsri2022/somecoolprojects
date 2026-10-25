# Social Media Tool

A Buffer-style tool to draft, edit, schedule, and post text posts to
LinkedIn and X — built for the Coding Challenges challenge
(https://codingchallenges.fyi/challenges/challenge-sm-tool).

## IMPORTANT: local-only, no real posting

This build uses **local fake platform adapters**. It never contacts
LinkedIn or X, never uses a real credential, and never posts to a real
account. The only credential references are placeholder environment
variable names (`LINKEDIN_ACCESS_TOKEN`, `X_BEARER_TOKEN`); they are
never read for a network call. A "posted" post gets a fake id like
`x:3` or `linkedin:3` and exists only in the local SQLite file.
See `docs/SPEC.md` for the full honest scope statement.

## Requirements

Python 3 (standard library only). No packages to install, no server,
no external service.

## Quick start

```bash
# Draft a post
python3 smtool.py create --platform x --author ada --body "Hello, world"

# Post immediately (via the local queue + fake adapter)
python3 smtool.py create --platform x --author ada --body "Hello now" --now

# Schedule a post
python3 smtool.py create --platform linkedin --author ada --body "Hi" \
    --schedule-at 2026-10-26T10:00:00Z

# List, inspect, edit, cancel
python3 smtool.py list
python3 smtool.py list --status scheduled --platform x
python3 smtool.py show 1
python3 smtool.py edit 1 --body "Edited text" --schedule-at 2026-10-27T09:00:00Z
python3 smtool.py edit 1 --clear-schedule   # back to a draft
python3 smtool.py cancel 1

# Post a draft/scheduled post right now
python3 smtool.py post-now 1

# Post everything whose scheduled time has arrived (single pass)
python3 smtool.py run-due

# Keep polling for due posts (Ctrl-C to stop), or do one pass
python3 smtool.py worker --interval 60
python3 smtool.py worker --once
```

By default the database is `social-media-tool.db` in the current
directory; pass `--db PATH` (before the subcommand) to use another file,
e.g. `python3 smtool.py --db /tmp/demo.db list`.

## Rules enforced

- Platforms: `linkedin`, `x` only.
- Body limits: X 280 chars, LinkedIn 3000 chars.
- Visibility: LinkedIn `public` / `connections`; X `public` only.
- Only `draft` / `scheduled` posts can be edited, cancelled, or posted
  now. A posted post is never re-posted.
- Past scheduled times are stored as-is and posted on the next
  `run-due` / `worker` pass (they are "due").

## Files

- `smtool.py` — the whole tool: CLI, SQLite store, queue, scheduler,
  fake adapters (single file, stdlib only).
- `docs/SPEC.md` — challenge steps, divergences, what is NOT built.
- `docs/DESIGN.md` — architecture, scheduler trade-off, queue semantics.
- `docs/TEST_PLAN.md` — coverage map.
- `tests/test_smtool.py` — unittest suite.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Expected: 28 tests, all passing, no network use.

## Challenge steps covered

Step 0 (setup, local-only) · Step 1 (queue-fed posting service) ·
Step 2 (SQLite post storage) · Step 3 (scheduling + polling worker) ·
Step 4 (create UI via CLI: draft / now / scheduled) ·
Step 5 (edit scheduled posts via CLI).

Deliberate divergences from the challenge page: CLI instead of a
web/GUI; SQLite queue + polling instead of ZeroMQ/RabbitMQ/cloud queue
or TTL trigger; fake adapters instead of real API calls; no user
authentication (the challenge only says to "consider" it); no media,
threads, analytics, or other platforms. All are documented in
`docs/SPEC.md`.
