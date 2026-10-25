# DESIGN — Social Media Tool

## Architecture (one file, stdlib only)

```
CLI (argparse subcommands)
  -> Store (sqlite3: posts + jobs tables)
  -> Queue (jobs table: enqueue / claim / complete / fail)
  -> Scheduler (poll: due scheduled posts -> queue -> drain)
  -> PlatformAdapter.post(post) -> FakeLinkedInAdapter / FakeXAdapter
```

Everything lives in `smtool.py`. No third-party packages, no network
access. The seams that would change for a real deployment are isolated:

- `PlatformAdapter` — one class per platform, one method `post(post)`.
  A real adapter would keep this signature and perform the HTTP call
  (LinkedIn share API / X create-tweet API) with the placeholder env
  tokens; the fake ones only validate and fabricate an id.
- `enqueue_job()` / `drain_queue()` — replace the `jobs` table with a
  broker (ZeroMQ/RabbitMQ/SQS) without touching CLI parsing or adapters.
- `find_due_posts()` — replace polling with a TTL/event trigger by
  calling the same enqueue path from the trigger instead of the loop.

## Scheduler trade-off (Step 3)

Polling was chosen over a TTL/event trigger because it needs no external
infrastructure, is easy to test deterministically (inject "now"), and is
correct for a single-user local tool: a due post is posted on the next
poll, at most one poll-interval late. Its costs are a wake-up per interval
even when idle, and latency bounded by the interval (default 60 s).
At multi-user/cloud scale a TTL/event trigger (e.g. DynamoDB TTL stream,
scheduled queue message) would be better: no idle polling, near-exact
timing, but it adds a managed service and makes local testing harder.
The `worker --interval` flag lets the operator trade latency for wake-ups.

## Queue semantics

- `post-now` and `run-due` enqueue exactly one pending job per post, then
  drain the queue synchronously in the same process. `worker` loops:
  enqueue due posts, drain, sleep.
- A job is claimed by marking it `processing` before the adapter call, so
  a second concurrent drain does not double-post the same job in the
  normal single-process case. Concurrent processes against one DB file are
  NOT protected beyond SQLite locking; run one worker per DB.
- On adapter success: job `done`, post `posted`, `posted_at` and
  `platform_post_id` recorded. On adapter exception: job `failed`, post
  `failed`, error text stored. No automatic retry (see SPEC).
- Idempotency: `run-due` only selects `scheduled` posts, and posting
  moves a post out of `scheduled`, so a second pass cannot re-post it.
  `post-now` rejects `posted`/`cancelled`/`queued` posts.

## Time handling

All stored times are UTC ISO-8601 strings (`YYYY-MM-DDTHH:MM:SS+00:00`,
second precision). `--schedule-at` accepts ISO-8601 with `Z` or an
offset; naive input is assumed UTC. Comparisons in SQL use these strings
lexicographically, which is safe because they are normalised to UTC
`+00:00` form before storage.

## Visibility and limits

| Platform | Max body chars | Allowed visibility |
|----------|---------------|--------------------|
| linkedin | 3000          | public, connections |
| x        | 280           | public             |

These mirror the real platforms' headline limits closely enough for a
local tool; they are enforced in `validate_post()` before storage and
again in each fake adapter before "posting", so a bad post cannot slip
through by editing the DB by hand and running `run-due` (the adapter
failure path marks it `failed` instead).

## Failure modes

- Invalid input (bad platform/visibility/length/unparseable time,
  conflicting flags, edit with no changes, edit/cancel/post-now on a
  post in the wrong state, unknown id): CLI exits non-zero with a clear
  message; nothing is stored or changed.
- Adapter failure: post becomes `failed` with the error; the operator can
  inspect with `show` and re-create the post. No silent loss: the post
  row and the failed job row both remain.
- Missing DB directory: SQLite creation fails with the OS error; the
  CLI does not create parent directories silently.

## Testing approach

See TEST_PLAN.md. Tests use `tempfile` DBs, call the Python API
(`create_post`, `edit_post`, `run_due`, `drain_queue`, adapters) directly
for most cases plus a CLI smoke test via `main([...])`, and never touch
the network or a real platform.
