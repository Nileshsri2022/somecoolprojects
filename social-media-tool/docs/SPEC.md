# SPEC — Social Media Tool

Source challenge: https://codingchallenges.fyi/challenges/challenge-sm-tool
(read 2026-10-25; page live, not a 404). The challenge is to build a
Buffer/HypeFury/Taplio-style tool to draft, edit and schedule posts, focused
on LinkedIn and X (formerly Twitter), covering a message queue, scheduling,
and RESTful API calls.

## Challenge steps and how each is met

- **Step 0 — Setup / sign up for LinkedIn or X APIs.**
  Met in local-only form only. No real API account is created, no real
  credential is requested, stored, or used, and no real platform is contacted.
  The only credential references are placeholder environment-variable names
  (`LINKEDIN_ACCESS_TOKEN`, `X_BEARER_TOKEN`); the fake adapters never read
  their values for a network call and never send them anywhere. Real API
  docs are linked in README for a future real adapter.
- **Step 1 — Backend service that listens to a message queue and posts.**
  Met with a local queue. `smtool.py` writes a job row into a `jobs` table
  (the queue) when a post is created for immediate posting or becomes due,
  and `worker` / `run-due` drains that queue and calls the platform adapter.
  The queue is SQLite-backed, not ZeroMQ/RabbitMQ/cloud queue (see
  Divergences). A job message carries: author, body, visibility, platform,
  post id, scheduled time.
- **Step 2 — Store a post in a database.**
  Met with SQLite (Python stdlib `sqlite3`). A post row holds: id, author,
  platform, body, visibility, status, scheduled_at (ISO-8601 UTC, nullable),
  created_at, updated_at, posted_at, platform_post_id, error.
  Statuses: `draft`, `scheduled`, `queued`, `posted`, `failed`, `cancelled`.
- **Step 3 — Schedule a post.**
  Met. `create --schedule-at <ISO time>` stores a `scheduled` post.
  `run-due` (and the `worker` loop, which polls) finds `scheduled` posts
  whose `scheduled_at <= now`, enqueues them, and posts them via the adapter.
  Trade-off note (see DESIGN.md): polling is simple and correct at this
  scale; a TTL/event trigger would scale better but needs external infra.
- **Step 4 — UI to create a post and post immediately or schedule it.**
  Met via CLI, not a web/GUI (see Divergences). `create` posts immediately
  with `--now`, or schedules with `--schedule-at`; without either flag it
  saves a `draft`.
- **Step 5 — UI to edit a scheduled post.**
  Met via CLI: `edit <id> [--body ...] [--schedule-at ...] [--visibility ...]`.
  Only `draft`/`scheduled` posts may be edited. Editing a `posted`,
  `cancelled`, `queued`, or `failed` post is rejected with an error.
  `cancel <id>` cancels a `draft`/`scheduled` post.
- **Going Further — other networks, other media types.**
  NOT built. Only LinkedIn and X text posts are supported. No images, video,
  threads, analytics, multi-user auth, or business features. See "NOT built".

## Commands (see README for full usage)

- `create --platform linkedin|x --author NAME --body TEXT [--visibility V]
  [--now | --schedule-at ISO] [--db PATH]`
- `list [--status S] [--platform P] [--author A] [--db PATH]`
- `show <id> [--db PATH]`
- `edit <id> [--body TEXT] [--schedule-at ISO | --clear-schedule]
  [--visibility V] [--db PATH]`
- `cancel <id> [--db PATH]`
- `post-now <id> [--db PATH]` — queue + post a draft/scheduled post now.
- `run-due [--db PATH]` — post all due scheduled posts, once.
- `worker [--interval SECONDS] [--once] [--db PATH]` — poll and post due
  posts; `--once` is a single pass (same as `run-due`).

## Validation rules (tested)

- Platform must be `linkedin` or `x` (case-insensitive, stored lowercase).
- Author and body are required and non-blank.
- Body length: X max 280 characters; LinkedIn max 3000 characters.
  Over-limit bodies are rejected before anything is stored.
- Visibility: LinkedIn allows `public`, `connections` (default `public`);
  X allows `public` only (default `public`). Any other value is rejected.
- `--schedule-at` must parse as ISO-8601 (a trailing `Z` is accepted);
  naive times are treated as UTC. Scheduling in the past is accepted and
  stored, so `run-due` posts it on the next pass (it is "due"), rather
  than silently failing or rewriting the time.
- `--now` and `--schedule-at` are mutually exclusive.
- `edit` with no change flags is rejected; `--clear-schedule` turns a
  scheduled post back into a draft.
- A post that has been posted is never re-posted: `run-due`/`worker` only
  touch `scheduled` posts, and `post-now` only accepts `draft`/`scheduled`.
  A failed adapter call marks the post `failed` with the error text and
  does not retry automatically (a later `post-now` may retry it only if it
  is `draft`/`scheduled`; a `failed` post must be re-created — see DESIGN).

## Divergences (deliberate, honest)

1. **CLI instead of a web/GUI.** Per the Wave 3 triage for this
   GUI/account-heavy challenge, the interface is a CLI. No HTML, no web
   server, no desktop GUI. All Step 4/5 interactions exist as CLI commands.
2. **Local fake platform adapters, no real posting.** The LinkedIn and X
   adapters are in-process fakes: they validate the same fields a real call
   would need, simulate a short local "post", and return a deterministic
   fake id (`linkedin:<post-id>`, `x:<post-id>`). They make NO network
   request and contact NO real platform. Nothing in this project posts to
   a real account. A real adapter would implement the same `post()`
   interface against the real REST APIs.
3. **SQLite queue + polling scheduler, not ZeroMQ/RabbitMQ/cloud queue
   or a TTL trigger.** The challenge suggests ZeroMQ/RabbitMQ or a cloud
   queue and a TTL/event trigger; this build uses a SQLite `jobs` table
   plus a polling loop so the whole project stays Python-stdlib-only with
   no external service. The queue/scheduler seam is explicit (jobs table +
   `drain_queue()`), so a real broker could replace it without changing
   the CLI or adapters.
4. **SQLite file instead of a hosted database.** Default DB is
   `social-media-tool.db` next to the invocation directory unless
   `--db` is given; tests use temp files. No server database is required.
5. **No user authentication.** The challenge says to "consider" adding
   user auth; it is not built. `author` is a free-text name, not an
   authenticated identity, and there is no login, session, or permission
   model. Anyone with the DB file can manage any post.
6. **No media, threads, or analytics.** Text posts only, one post per
   command, no attachments, no thread/reply support, no engagement stats.

## NOT built (honestly)

- Real LinkedIn/X API calls, OAuth, or any real account posting.
- Web UI, GUI, hosted service, or cloud deployment.
- ZeroMQ/RabbitMQ/cloud message queue; DynamoDB TTL or event trigger.
- User accounts/authentication, multi-user isolation, roles.
- Media attachments, threads, polls, analytics, other platforms.
- Automatic retries, backoff, rate-limit handling against a real API
  (the fake adapter never rate-limits; a failed fake post is terminal
  for that attempt, see Validation rules).
- Any background daemon/service installation (worker runs in foreground
  until Ctrl-C, or `--once`).

## Data model

See DESIGN.md. Storage is a single SQLite file with `posts` and `jobs`
tables, created automatically on first use.
