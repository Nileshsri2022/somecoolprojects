# Blogging Software — DESIGN

## Stack

- Python 3, standard library only: `argparse`, `sqlite3`, `http.server`,
  `html`, `hashlib`, `datetime`, `xml.etree`-free hand-built RSS
  (escaped strings), `urllib.parse`.
- One main file: `blog.py`. No helpers, no third-party packages, no
  build step. Tests live in `tests/test_blog.py` (stdlib `unittest`).

## Data model (SQLite)

```sql
posts(id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
      body TEXT NOT NULL DEFAULT '',
      published_at TEXT NOT NULL,   -- ISO-8601, set on creation
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
comments(id INTEGER PRIMARY KEY AUTOINCREMENT,
         post_id INTEGER NOT NULL REFERENCES posts(id),
         name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',
         body TEXT NOT NULL, created_at TEXT NOT NULL);
```

- `published_at` defaults to creation time (UTC, `...Z` form) when the
  caller does not supply one; `edit` may override it explicitly.
- Ordering everywhere is `published_at DESC, id DESC` for posts and
  `created_at DESC, id DESC` for comments, giving newest-first order
  with a deterministic tiebreak.
- `BlogStore` wraps all SQL: `create_post`, `get_post`, `list_posts`,
  `update_post`, `delete_post`, `add_comment`, `list_comments`.
  `create_post`/`update_post` reject an empty title or an empty body
  (`ValueError`); `add_comment` rejects an empty name or body, and
  rejects comments on a nonexistent post (`LookupError`).
  `update_post` on a missing id raises `LookupError`.

## Rendering

- `escape_html` via `html.escape` for all user content, always.
- `markdown_to_html(text)`: line-based, in order — blank-line
  paragraph breaks, `#`/`##`/`###` headings, `-`/`*` unordered lists,
  then inline `code`, `**bold**`, `*italic*`, `[text](url)` (only
  `http(s)://` and `/`-relative hrefs are kept; anything else renders
  as plain text). Raw HTML in the source is escaped before inline
  processing, so it can never inject markup.
- Templates are functions returning full HTML documents sharing one
  layout (`layout(title, body)`): `render_index(posts)`,
  `render_post(post, comments)`, `render_editor_index(posts)`,
  `render_post_form(post)`, `render_login(error)`. No template files.
- RSS: `render_feed(posts)` builds RSS 2.0 with escaped titles,
  summaries (as description) and links of the form `/posts/<id>`.

## HTTP server

- `make_handler(store, password)` returns a `BaseHTTPRequestHandler`
  subclass; `serve(store, host, port, password)` runs
  `ThreadingHTTPServer`. Default host `127.0.0.1`, default port 8080
  (the challenge's port); tests bind port 0 (ephemeral).
- Routes:
  - `GET /` → index, newest first, titles link to `/posts/<id>`.
  - `GET /posts/<id>` → post + comment form + comments newest first.
  - `POST /posts/<id>/comments` → form fields `name`, `email`,
    `comment`; on success redirects back to the post; on validation
    error re-renders the post with an error note.
  - `GET /feed.xml` → RSS.
  - `GET /login`, `POST /login` → password form; success sets
    `blog_admin=<sha256(password)>` cookie and redirects to `/editor`.
  - `GET /editor` → requires auth, else 302 to `/login`; lists posts
    with edit links and a "new post" link.
  - `GET /editor/post` → new-post form; `POST /editor/post` → creates.
  - `GET /editor/post/<id>` → edit form prefilled; `POST` → updates.
  - Unknown paths → 404; non-integer post ids → 404; wrong-method
    editor POSTs without auth → redirect to `/login`.
- Auth check: `is_authenticated(handler)` compares the request's
  `blog_admin` cookie to `sha256(password)`. Documented local-only
  limitation (see SPEC).

## CLI

`python3 blog.py [--db PATH] <command> ...` — global `--db` defaults
to `blog.db` next to `blog.py` (tests pass a temp path explicitly).

- `create --title T --summary S --body B [--published-at ISO]`
  (also `--body-file PATH`); prints the new post id.
- `edit ID [--title T] [--summary S] [--body B] [--body-file PATH]
  [--published-at ISO]`
- `list` — newest first, one line per post: `id | published | title`.
- `show ID` — title, summary, dates, then raw Markdown body.
- `comment ID --name N [--email E] --text T`
- `delete ID`
- `serve [--host H] [--port P] [--password PW]` — `BLOG_PASSWORD`
  env var is the fallback when `--password` is omitted.

## Error handling

- CLI: missing post → `LookupError` message + exit code 1 via a
  `main()` catch; argparse errors exit 2 (standard).
- HTTP: missing post → 404 page; validation errors → the same form
  re-rendered with an error message and HTTP 400 for comment posts,
  400 for editor posts (create/edit with empty title/body).
