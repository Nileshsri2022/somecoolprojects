# DESIGN.md — Web Server

## Assumptions (stated before coding, per workflow)

1. **Stdlib HTTP machinery, not raw sockets.** `http.server.ThreadingHTTPServer`
   + `BaseHTTPRequestHandler` is the smallest correct implementation:
   it already parses the request line, headers, and keep-alive correctly.
   Hand-rolling socket parsing would add code and bug surface for no
   benefit in a static-file server. This is a deliberate simplicity
   choice under the ponytail guidelines, not a shortcut around the
   challenge: all routing, status, content-type, and traversal logic is
   ours.
2. **One root, resolved once.** The root directory is resolved to an
   absolute, symlink-resolved path at server creation. Every request
   path is joined to it and resolved the same way, then checked to be
   inside the root (`Path.is_relative_to`, with a fallback for older
   Pythons via `os.path.commonpath`). Anything outside → 403, before
   any file is opened. This covers `..`, `%2e%2e`, and symlinks
   pointing outside the root.
3. **No directory listing.** A directory request serves `index.html`
   inside it, else 404. Listing would leak filenames and needs HTML
   generation the challenge's core (serve files, status, content type)
   does not require.
4. **Files are read whole into memory.** Simplicity first: static
   test-sized files do not need chunked streaming. `Content-Length`
   is then exact, which also makes HEAD trivial (same headers, skip
   the body write).
5. **Single handler factory.** `make_handler(root)` returns a handler
   class closing over the resolved root, so tests can build a server
   on an ephemeral port without subprocesses or hard-coded ports, and
   the CLI reuses exactly the same code path.
6. **Method handling.** `do_GET` and `do_HEAD` share one `_serve`
   method (`head_only` flag). `do_POST`, `do_PUT`, `do_DELETE`,
   `do_PATCH`, `do_OPTIONS` all return 405 with an `Allow: GET, HEAD`
   header. Unknown methods fall through to `BaseHTTPRequestHandler`'s
   default 501, which is acceptable and documented, not hidden.
7. **Content types via `mimetypes`.** No hand-maintained extension
   table to drift. The one normalisation: `text/*` types gain
   `; charset=utf-8`. Note: `mimetypes` may report `.js` as
   `text/javascript` on some platforms and `application/javascript`
   on others; tests therefore accept either for `.js`.
8. **Errors have bodies.** 403/404/405 responses include a short plain-text
   body and a matching `Content-Length`, so clients (including the
   tests' `http.client`) read a complete, well-formed response instead
   of hanging on keep-alive.
9. **Logging.** Default handler logging to stderr is kept (one line per
   request); it is not silenced, because a server that logs nothing is
   harder to debug. Tests do not depend on log output.

## Module layout (`web_server.py`, single file)

- `make_handler(root)` — handler class factory.
- `create_server(host, port, root)` — returns a `ThreadingHTTPServer`
  (not yet serving), so tests can start it on port 0 in a thread.
- `serve(host, port, root)` — create + `serve_forever()`; used by CLI.
- `parse_args(argv)` / `main(argv)` — CLI, exit code 0 on normal
  shutdown (KeyboardInterrupt is caught and exits cleanly).

## Request flow

```
GET /a/b.txt?x=1
  -> strip query, unquote path
  -> join root + path, resolve
  -> outside root?           -> 403
  -> is directory?           -> append index.html, else 404
  -> not a regular file?     -> 404
  -> read bytes, guess type  -> 200 + Content-Type + Content-Length
HEAD: same, body omitted.
```

## Verifiable success criteria

- `python3 -m unittest discover -s tests -v` passes, 100%.
- Manual check (killed by explicit PID afterwards): start the server
  on a test port, `curl` an HTML file, a CSS file, a missing file,
  and a traversal attempt, and observe 200 / 200 / 404 / 403.
