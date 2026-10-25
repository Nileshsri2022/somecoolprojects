# Blogging Software — TEST_PLAN

Runner: `python3 -m unittest discover -s tests -v` from the project
directory. Standard library only. Every test uses a temporary SQLite
file (or `:memory:`) and, for HTTP tests, an ephemeral port
(`port 0`); servers are shut down in `tearDown` and no test leaves a
process behind.

## Coverage map

Store (unit, no HTTP):
- create → get round-trip preserves title, summary, body, dates.
- `published_at` defaults to creation time when not supplied, and an
  explicit value is stored verbatim.
- `list_posts` returns newest-first by `published_at`, with `id DESC`
  tiebreak.
- `update_post` changes fields, bumps `updated_at`, optionally changes
  `published_at`; updating a missing id raises `LookupError`.
- Empty title / empty body on create and on update raise `ValueError`.
- `delete_post` removes the post (missing id → `LookupError`).
- `add_comment` + `list_comments`: newest-first order; empty name or
  body raises `ValueError`; commenting on a missing post raises
  `LookupError`; comment email is stored but not rendered (checked
  via `render_post` output).

Rendering (unit):
- Markdown: headings, paragraphs, bold, italic, inline code, links,
  unordered lists; raw HTML in input is escaped, never emitted.
- `render_index`: titles link to `/posts/<id>`, newest-first order,
  empty store shows "No posts yet".
- `render_post`: body HTML + comments newest-first present.
- `render_feed`: valid RSS shape, one `<item>` per post, escaped titles.

HTTP (live server on an ephemeral port, `urllib` client):
- `GET /` returns 200 and lists post titles as links, newest first.
- `GET /posts/<id>` returns 200 with the post body and its comments.
- `GET /posts/99999` returns 404; `GET /nope` returns 404.
- `GET /editor` without a login cookie redirects to `/login`.
- Login flow: `POST /login` with the right password sets the cookie
  and the editor then returns 200; wrong password re-renders login
  with an error.
- Editor create: authenticated `POST /editor/post` creates a post
  visible at `/posts/<id>` and on `/`.
- Comment flow: `POST /posts/<id>/comments` adds a comment shown on
  the post page.
- `GET /feed.xml` returns 200 with `rss` content.

CLI (subprocess, temp db):
- `create` prints an id; `list` shows it; `show` prints its body;
  `comment` + `show`-via-HTTP-free check: `list`/`show` unaffected;
  `edit` changes the title visible in `list`.
- `serve` smoke test is covered by the HTTP suite (not by spawning a
  second long-lived server in CLI tests).

## Manual checks (done once, not automated)

- `python3 blog.py serve --port 8080`, then `curl -i
  http://localhost:8080/` — expect `200 OK` and the index page
  (mirrors the challenge's Step 1 curl example, minus the seeded
  sample post, per the SPEC divergence note).
- Visit `/editor` in a browser, log in, create and edit a post, add a
  comment — the same flows the HTTP tests exercise programmatically.
