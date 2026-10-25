# Blogging Software — SPEC

Source: https://codingchallenges.fyi/challenges/challenge-blog
("Build Your Own Blogging Software", read 2026-10-25. Page live, not a 404.)

## What the challenge asks

A simple blogging platform: write and edit posts, render them as HTML
using a common layout, and let readers comment on posts.

- Step 0 — Pick a language/IDE and set up a project.
- Step 1 — Serve a static web page on the developer machine (page uses
  port 8080; `curl -i http://localhost:8080/` returns a `My Blog` page
  with a first post).
- Step 2 — Turn the index page into a template (`{{postlist}}`-style
  placeholder) filled from datastore data, e.g. JSON posts with
  `title`, `summary`, `post` fields. Visiting the blog shows the same
  result as Step 1.
- Step 3 — Web authoring:
  1. An admin section (suggested `/editor`), authenticated, otherwise
     redirected to a login page.
  2. A page to create a new post (suggested `/editor/post`): title,
     summary, post body, Markdown encouraged for formatting.
  3. On save, the post is persisted (page suggests a Markdown/JSON file
     at this stage).
  4. The post renders at a suitable URL (e.g. `/posts/1`).
- Step 4 — Editing: log in, pick a post from a list, edit its fields.
  Add a published date/time, set on creation, optionally updatable
  on edit.
- Step 5 — Store posts in a database (SQL or NoSQL) instead of a text
  file; consider the tradeoffs.
- Step 6 — Homepage lists posts from the database, newest to oldest,
  each title a link to the full post.
- Step 7 — Comments: a reader enters name, email and comment on a post;
  comments render under the post, newest to oldest.
- Going Further — RSS feeds; editing the template through `/editor`;
  scheduling a post.

## What this build does

Python 3 standard library only, one main file (`blog.py`):

- CLI for the full core: `create`, `edit`, `list`, `show`, `comment`,
  `serve` (see README for exact usage).
- Local HTTP server (default port 8080, matching the challenge):
  `GET /` homepage, `GET /posts/<id>` full post + comments,
  `GET /feed.xml` RSS feed, `GET /login`, `GET /editor`,
  `GET|POST /editor/post` (new), `GET|POST /editor/post/<id>` (edit),
  `POST /posts/<id>/comments` (public comment form on the post page).
- Storage: SQLite (stdlib `sqlite3`), tables `posts` and `comments`.
  This is the Step 5 database, adopted from the start (see divergence).
- Posts: title, summary, Markdown body, `published_at` (set on
  creation, editable on edit), `created_at`/`updated_at` bookkeeping.
- Comments: name, email, body, `created_at`; rendered newest first.
- Markdown: a small built-in subset — headings (`#`–`###`),
  paragraphs, `**bold**`, `*italic*`, `` `code` ``, `[text](url)`,
  unordered lists (`-`/`*`). No external Markdown library (stdlib only).
- Templates: small Python string templates in `blog.py` (one shared
  page layout); no external templating engine.
- Auth: local-only password gate for `/editor`. The password comes
  from `--password` / `BLOG_PASSWORD` (default `admin`, for local
  development only). A successful login sets a cookie holding a
  SHA-256 hash of the password; the editor checks it and redirects
  unauthenticated visitors to `/login`. This is NOT production
  authentication (no rate limiting, no salted password storage, no
  HTTPS, no CSRF token).

## Deliberate divergences (honest)

1. Step 3 file stage skipped: posts go straight to SQLite instead of
   first being written as a Markdown/JSON file and later migrated.
   Rationale: the challenge's own Step 5 destination is a database,
   and the JSON-file stage would be throwaway work. The final
   behaviour (create via editor, render at `/posts/<id>`) is identical.
   Tradeoff recorded: SQLite is a single-file local database — no
   concurrent multi-writer scaling, no remote hosting; fine for a
   local blog, not a multi-author hosted service.
2. Step 2's `{{postlist}}` placeholder syntax is not used literally;
   the same idea is implemented as Python template functions
   (`render_index`, `render_post`) that fill a shared layout. The
   observable result (index filled from stored posts) is the same.
3. No `My Blog` hard-coded sample post is seeded. The homepage with
   an empty database shows an explicit "No posts yet" message, and
   the first post is created through the CLI or the editor. Seeding
   fake content would misrepresent the store's state.
4. Editor URLs follow the page's suggestions exactly (`/editor`,
   `/editor/post`, `/posts/<id>`), plus `/editor/post/<id>` for edits
   (the page says "select a post from a list and then edit it"; the
   editor index lists posts with edit links).
5. Comment email is stored but never displayed publicly (spam/
   privacy hygiene); name, body and date are displayed. The page does
   not require displaying the email.
6. RSS (`/feed.xml`) IS built, although listed only under Going
   Further — it is a small, honest addition, not a claim beyond it.

## NOT built (scope limits)

- Hosting / deployment: no hosted or public blog. The server binds
  localhost by default and is a local preview only. Any hosting or
  deploy steps from the challenge's framing are NOT built.
- Template editing through `/editor`: NOT built. Templates live in
  `blog.py` and are changed by editing the source.
- Post scheduling: NOT built. There is no scheduled/draft state and
  no publish-at-in-the-future behaviour; `published_at` is a
  timestamp field, and every created post is immediately listed.
- No user accounts, roles, or multi-author support: one shared admin
  password only.
- No comment moderation, spam filtering, or deletion UI (comments can
  only be added; posts can be deleted via CLI `delete` only).
- No full Markdown (no tables, images with alt handling beyond link
  syntax, code blocks, or HTML passthrough — raw HTML in post bodies
  is escaped, never rendered).
- No search, tags/categories, pagination, or themes.
- No production hardening: no HTTPS/TLS, no CSRF protection, no
  rate limiting, no input-size limits beyond what the stdlib server
  imposes. Do not expose this server to the public internet.

## Success criteria

- `python3 blog.py list` / `create` / `show` round-trip through SQLite.
- `python3 blog.py serve` on an ephemeral test port serves `/`
  (newest-first linked titles), `/posts/<id>` (body + newest-first
  comments), `/feed.xml`, and redirects unauthenticated `/editor`
  to `/login`.
- Full unittest suite green (see `docs/TEST_PLAN.md`).
