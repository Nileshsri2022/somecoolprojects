# TEST_PLAN — Social Media Tool

Run: `python3 -m unittest discover -s tests -v` from the project directory.
Python 3 standard library only; no network, no real platform, no server.
All tests use temporary SQLite files (tempfile) and are deleted by the
test harness. Expected result: all tests pass, 0 failures, 0 errors.

## Coverage map

1. Create (happy path): LinkedIn + X posts stored with correct fields,
   default visibility `public`, draft status when no flag given.
2. Create immediate: `--now`-equivalent API path produces a `posted`
   post with a fake platform id (`linkedin:<id>` / `x:<id>`) and
   `posted_at` set, via the queue.
3. Create scheduled: `--schedule-at` stores `scheduled` status and the
   normalised UTC time; the post is NOT posted before its time.
4. Validation rejects: blank author, blank body, unknown platform,
   X body > 280 chars, LinkedIn body > 3000 chars, invalid visibility
   (e.g. `connections` on X, `friends` anywhere), unparseable
   `--schedule-at`, both `--now` and `--schedule-at`, and stores nothing
   on rejection (post count unchanged).
5. List/show: list returns all posts newest-first (by id desc); filters
   by status, platform, author work; `show` returns one post; unknown
   id raises/returns an error.
6. Edit scheduled: body and schedule time and visibility can be changed;
   `--clear-schedule` returns a scheduled post to `draft`; edit with no
   change flags is rejected; editing a `posted` or `cancelled` post is
   rejected and leaves the post unchanged.
7. Cancel: cancels draft/scheduled; cancelling a posted post is rejected;
   a cancelled post is never posted by `run-due`.
8. Scheduler: `run_due` posts only due scheduled posts (past time),
   leaves future posts `scheduled`, does not re-post already-posted
   posts, and posts multiple due posts in one pass.
9. Post-now: posts a draft/scheduled post now; rejects posted/cancelled
   posts; a post-now on a scheduled post clears its future schedule
   effect (status becomes `posted`, it is not re-posted later).
10. Queue: enqueue creates a pending job; drain marks job `done` and the
    post `posted`; a failing adapter marks job `failed` and post
    `failed` with the error stored (tested with a stub adapter that
    raises, injected via the adapter registry).
11. Adapters: fake LinkedIn/X adapters return the expected fake id
    format and reject over-limit bodies / bad visibility even when
    called directly (defence in depth).
12. CLI smoke: `main(["create", ...])`, `main(["list"])`,
    `main(["show", id])`, `main(["edit", ...])`, `main(["cancel", ...])`,
    `main(["run-due"])` succeed end-to-end through argparse against a
    temp DB; an invalid CLI invocation exits non-zero.
13. Persistence: a post created through one `Store` instance is visible
    through a fresh `Store` on the same file (round-trip).

## What is NOT tested (honestly)

- Real LinkedIn/X APIs, OAuth flows, or network behaviour: there is no
  real adapter and no network call to test.
- Concurrent workers against one DB: single-worker use is the supported
  mode (see DESIGN.md); no concurrency test is claimed.
- Long-running `worker` loop timing: tests cover the single-pass
  (`--once` / `run_due`) path; the sleep loop itself is not
  time-tested beyond one iteration with a tiny interval.
