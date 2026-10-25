# SPEC.md — Web Server (Coding Challenges #11)

## Challenge source — IMPORTANT CAVEAT

The task directed that the challenge page at
`https://codingchallenges.fyi/challenges/challenge-web-server/` be read
first and built from. That URL is a confirmed 404 on the site
(verified twice on 2026-10-25: text fetch and a live-browser read
both returned the site's "Page Not Found" page), and a web search
found no alternative Coding Challenges web-server challenge page.
No corrected slug was established, so the page's exact step
wording could NOT be verified. The spec below is therefore the
standard static-file HTTP server behaviour that a web-server
challenge is built around, implemented conservatively (stdlib
only, no framework features). Any step wording that differs
from a live page should be treated as a deliberate divergence,
listed in the final report, not as a quote from the page.

## Goal

A small HTTP server, Python 3 standard library only, that serves static
files from a directory over HTTP, with correct status codes and
content types.

## Behaviour

1. **Serve static files.** `GET /path/to/file` returns the file's bytes
   from the configured root directory.
2. **Root / index.** `GET /` serves `index.html` from the root when it
   exists; otherwise 404 (no directory listing — see DESIGN.md).
3. **Status codes.**
   - `200 OK` — file found and served.
   - `404 Not Found` — no such file, or a directory with no `index.html`.
   - `403 Forbidden` — the resolved path escapes the root directory
     (path traversal, including `..`, percent-encoded `..`, and symlink
     escape).
   - `405 Method Not Allowed` — any method other than `GET`/`HEAD`
     (e.g. `POST`, `PUT`, `DELETE`).
4. **Content types.** Determined from the file extension via
   `mimetypes` (e.g. `.html` → `text/html`, `.css` → `text/css`,
   `.js` → `text/javascript` or `application/javascript` as the platform
   reports, `.json` → `application/json`, `.png` → `image/png`,
   `.txt` → `text/plain`). Unknown extensions fall back to
   `application/octet-stream`. A `charset=utf-8` suffix is added for
   `text/*` types.
5. **HEAD.** Same status and headers as `GET` for the same path, but
   with an empty body. `Content-Length` still reports the file size.
6. **Headers.** Every response carries `Content-Length` (and
   `Content-Type` for 200 responses), so HTTP/1.1 keep-alive works and
   clients do not have to rely on connection close to find the end
   of the body.
7. **URL handling.** The query string is ignored for file lookup.
   Percent-encoded paths are decoded before lookup, so
   `/hello%20world.txt` finds `hello world.txt`.
8. **Concurrency.** Threaded: one slow client must not block others.
9. **CLI.**
   - `python3 web_server.py [--host HOST] [--port PORT] [--directory DIR]`
   - Defaults: host `127.0.0.1`, port `8080`, directory = current
     working directory.
   - `--port 0` is accepted (OS-assigned ephemeral port, used by tests).

## Non-goals (deliberately out of scope)

- No CGI, no dynamic templating, no reverse proxying, no TLS.
- No directory listings, no range requests, no caching headers
  (`ETag`/`Last-Modified` handling), no compression.
- No authentication. This is a local static-file server, not a
  production deployment.
