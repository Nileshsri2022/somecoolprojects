# Blogging Software

Build Your Own Blogging Software, from
https://codingchallenges.fyi/challenges/challenge-blog
(Steps 0–7; see `docs/SPEC.md` for the full mapping).

Local blog core in Python 3, standard library only: create/edit/list
posts, SQLite storage, comments, and a local HTTP preview with an
editor section and an RSS feed. **No hosted/deployed blog** — the
server is a localhost preview only (see scope limits below).

## Run

```sh
# Create and list posts
python3 blog.py create --title "My First Blog Post" \
  --summary "The first blog post I've written on my blogging software!" \
  --body "# Hello

This is my first blog post content..."
python3 blog.py list
python3 blog.py show 1
python3 blog.py edit 1 --title "My First Blog Post (revised)"
python3 blog.py comment 1 --name "Ana" --email "ana@example.com" --text "Great post!"

# Serve locally (default http://127.0.0.1:8080, the challenge's port)
python3 blog.py serve
# With an explicit editor password (or set BLOG_PASSWORD):
python3 blog.py serve --password mysecret
# Use a different database file:
python3 blog.py --db myblog.db serve --port 8090
```

## Web routes

| Route | What it does |
| --- | --- |
| `GET /` | Homepage: posts newest first, titles link to full posts |
| `GET /posts/<id>` | Full post + comments (newest first) + comment form |
| `POST /posts/<id>/comments` | Add a comment (name, email, comment) |
| `GET /feed.xml` | RSS 2.0 feed |
| `GET /login`, `POST /login` | Editor login (default password `admin`, local dev only) |
| `GET /editor` | Post list with edit links (login required, else redirects to `/login`) |
| `GET\|POST /editor/post` | Create a post (title, summary, Markdown body, published date) |
| `GET\|POST /editor/post/<id>` | Edit a post |

Markdown supported: `#`–`###` headings, paragraphs, `**bold**`,
`*italic*`, `` `code` ``, `[text](url)`, unordered lists. Raw HTML in
post bodies is escaped, never rendered.

## Tests

```sh
python3 -m unittest discover -s tests -v
# 25 tests, all passing (store, rendering, live HTTP, CLI)
```

## Docs

- `docs/SPEC.md` — challenge steps, divergences, NOT-built list
- `docs/DESIGN.md` — data model, rendering, HTTP routes, CLI
- `docs/TEST_PLAN.md` — coverage map

## Scope limits (honest)

- NOT built: hosting/deployment (localhost preview only), template
  editing through `/editor`, post scheduling (no draft/scheduled
  state — every post is immediately listed), user accounts/roles,
  comment moderation, search/tags/pagination/themes, full Markdown.
- The editor password gate is local-only: unsalted SHA-256 cookie,
  no CSRF protection, no HTTPS, no rate limiting. Do not expose this
  server to the public internet.
- Divergence: posts go straight to SQLite (the challenge's Step 5
  destination) instead of first using a JSON file and later migrating
  (Step 3's interim suggestion). No sample post is seeded; an empty
  blog shows "No posts yet".
