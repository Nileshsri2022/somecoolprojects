# TEST_PLAN.md — Web Server

## Harness

- `unittest`, in `tests/test_web_server.py`.
- One live server per test class (`setUpClass`/`tearDownClass`):
  `create_server("127.0.0.1", 0, root)` — port 0 = OS-assigned
  ephemeral port, read back from `server.server_address[1]`. No
  hard-coded ports anywhere.
- Server runs in a daemon thread; `tearDownClass` calls
  `shutdown()` + `server_close()`, so no test server survives the run.
- Requests use stdlib `http.client.HTTPConnection` (real HTTP over a
  real socket, not a direct handler call).
- Fixture root is a `tempfile.TemporaryDirectory` populated per class:
  `index.html`, `style.css`, `app.js`, `data.json`, `hello.txt`,
  `hello world.txt` (percent-encoding case), `pic.png` (binary bytes),
  `sub/page.html`, `sub/` (no index — directory case), `unknown.foobar123`
  (fallback content type), plus an outside-root file and a symlink
  inside the root pointing outside it (traversal cases).

## Cases

1. `test_get_index_at_root` — `GET /` → 200, body = index.html,
   `Content-Type` contains `text/html`.
2. `test_get_html_file` — `GET /index.html` → 200, exact bytes.
3. `test_get_css_content_type` — `GET /style.css` → 200,
   `text/css`.
4. `test_get_js_content_type` — `GET /app.js` → 200,
   `text/javascript` or `application/javascript` (platform variance).
5. `test_get_json_content_type` — `GET /data.json` → 200,
   `application/json`.
6. `test_get_text_content_type` — `GET /hello.txt` → 200,
   `text/plain`.
7. `test_get_binary_png` — `GET /pic.png` → 200, exact binary bytes,
   `image/png`.
8. `test_get_subdirectory_file` — `GET /sub/page.html` → 200.
9. `test_get_directory_without_index_404` — `GET /sub/` → 404.
10. `test_get_missing_404` — `GET /nope.html` → 404.
11. `test_query_string_ignored` — `GET /hello.txt?v=1` → 200, same body.
12. `test_percent_encoded_path` — `GET /hello%20world.txt` → 200.
13. `test_head_same_headers_no_body` — `HEAD /hello.txt` → 200,
    `Content-Length` = file size, body empty.
14. `test_head_missing_404` — `HEAD /nope.html` → 404, body empty.
15. `test_post_405` — `POST /hello.txt` → 405, `Allow` mentions GET.
16. `test_traversal_dotdot_403` — `GET /../outside.txt` → 403
    (http.client normalises some forms, so this case also asserts via
    the encoded form below; both are kept).
17. `test_traversal_encoded_403` — `GET /%2e%2e/outside.txt` → 403.
18. `test_symlink_escape_403` — `GET /link-outside.txt` → 403, where
    the symlink points to a file outside the root.
19. `test_unknown_extension_octet_stream` — `GET /unknown.foobar123` → 200,
    `application/octet-stream`.
20. `test_content_length_matches_body` — `GET /hello.txt` →
    `Content-Length` equals `len(body)`.

## Manual check (not part of the suite)

Start `python3 web_server.py --port <free> --directory <fixture>`,
curl `/`, a `.css` file, a missing path, and `/../` traversal;
expect 200 / 200 / 404 / 403. Kill the server by explicit PID only.
