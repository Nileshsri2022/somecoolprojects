# TEST_PLAN — curl clone

All tests run against a local `http.server.ThreadingHTTPServer` on an
ephemeral port (`port 0`, OS-assigned), started in `setUpClass` and
shut down in `tearDownClass`. No test touches the internet or
httpbin: the page's examples use httpbin, but depending on it would
make the suite flaky and slow. The handler echoes what it received
(method, path, headers, body) as JSON, plus special routes:

- `/get`, `/delete`, `/post`, `/put`, `/patch` — echo endpoints.
- `/headers` — echoes received request headers as JSON.
- `/redirect` — 302 to `/get` (absolute Location).
- `/redirect-relative` — 302 to `get` (relative Location, resolved
  against the current URL).
- `/redirect-post` — 302 to `/get`; used to check POST -> GET rewrite.
- `/redirect-307` — 307 to `/post`; used to check method/body kept.
- `/redirect-loop` — 302 to itself; used to check the max-redirs error.
- `/status/404`, `/status/500` — fixed statuses with a body.
- `/head` — responds to HEAD with headers and no body.
- `/chunked` — chunked transfer-encoding body (exercises framing).

## Cases (library level, via `request()` / `parse_url` / `build_headers`)

1. `parse_url`: http default port 80, https 443, explicit port kept,
   missing path -> `/`, query preserved, fragment dropped, host
   header omits default port / includes non-default port.
2. `parse_url` errors: no scheme, `ftp://` scheme, missing host,
   non-numeric port — each raises `CurlError` with code 3.
3. GET returns 200 and the exact body; echoed method is GET.
4. `-X DELETE` / PUT / PATCH reach the server with that method.
5. POST with `-d` JSON and `-H Content-Type` arrives byte-identical;
   server sees `Content-Length` equal to the byte length.
6. `-d` without `-X` implies POST.
7. Custom `-H` headers arrive; a user `Accept:` replaces the default.
8. `Content-Length` supplied via `-H` is respected, not duplicated.
9. Verbose mode emits `> GET ...` and `< HTTP/1.1 200 ...` lines.
10. HEAD returns headers and an empty body.
11. Chunked response body is read in full.
12. Redirects without `-L`: 302 response returned as-is, body intact.
13. Redirects with `-L`: absolute and relative chains land on `/get`
    with status 200; POST -> GET on 302 (body dropped, method GET);
    307 keeps POST and its body; loop hits the max-redirs error
    (code 47).
14. `-f` behaviour: 404 without `-f` returns body + exit path 0 at
    library level (status 404 in the Response); the CLI-level test
    checks exit 22 and no body with `-f`.

## Cases (CLI level, subprocess running `curl.py` against the server)

15. Default run prints only the body (no headers) to stdout, exit 0.
16. `-v` run prints body on stdout and `>`/`<` lines on stderr.
17. `-i` run prints status line + headers before the body on stdout.
18. `-o FILE` writes the body to FILE and prints nothing to stdout;
    the file content equals the body byte-for-byte.
19. `-f` on a 404: exit 22, stderr message, empty stdout.
20. Connection refused (server port closed): exit 7, stderr message,
    empty stdout.
21. No URL / unknown option / malformed `-H` (no colon): exit 2 or 3
    respectively, usage-ish message on stderr.
22. Binary-ish body round-trips through `-o` unchanged.

## Manual checks (not in the suite, done once during development)

- Against system curl 8.5.0 on the same local server: GET, POST with
  JSON, `-X DELETE`, `-v` output shape, and `-o` file contents agree
  (modulo the documented User-Agent / `*` verbose-line divergences).
- `curl.py https://example.invalid/` fails with a DNS-style error,
  not a traceback (no live HTTPS test in the suite: no external
  dependency; HTTPS code path is the same `send_once` with
  `HTTPSConnection`).

## Command

```sh
cd ~/workspace/somecoolprojects/curl
python3 -m unittest discover -s tests -v
```
