# TEST_PLAN — URL Shortener

Suite: `tests/test_url_shortener.py`, `unittest`, run from the project
root with `python3 -m unittest discover -s tests -v`.

Each test class starts a real `ThreadingHTTPServer` on an ephemeral
port (`port=0`, OS-assigned) in `setUp` and shuts it down in
`tearDown`. All checks use real HTTP requests (`urllib.request` /
`http.client`); no port is hard-coded and no handler is called
directly. Tests that must observe a 302 without following it use
`http.client` (urllib follows redirects by default).

## Cases

Create (POST /):

1. Valid URL → 201, JSON has `key` (6 base62 chars), `long_url`
   echoing the input, and `short_url` ending in `/<key>`.
2. Idempotent create → same URL posted twice returns the same key,
   same status, and the store still holds exactly one mapping
   (checked via a second redirect + a fresh key count through the
   handler's store).
3. Two different URLs → different keys.
4. Missing `url` field → 400, body `Missing field: url`.
5. Malformed JSON body → 400, body starts with `Invalid JSON`.
6. Wrong-type `url` (e.g. a number) → 400.
7. Empty string URL → 400.
8. URL without scheme/host (`notaurl`) → 400.
9. Non-http(s) scheme (`ftp://…`) → 400.
10. Non-object JSON (e.g. a list) → 400.

Redirect (GET /<key>):

11. Known key → 302, `Location` header exactly the long URL, empty body.
12. Unknown key → 404, body `URL not found`.
13. `GET /` (no key) → 404, body `URL not found`.
14. Redirect follows create: the `short_url` path from a create
    response redirects to the original URL.

Delete (DELETE /<key>):

15. Existing key → 200, empty body; subsequent GET → 404.
16. Unknown key → 200, empty body (no action), and an unrelated
    existing key still redirects.
17. Deleted URL can be re-created: POST after delete returns the same
    key and redirects again.

Key generation (unit, no HTTP):

18. Same input → same key; different inputs → different keys
    (spot-checked).
19. Forced collision: pre-seed the store with a key that a new URL
    would hash to, mapped to another URL → the new URL still gets a
    distinct, working key (re-hash with salt path).
20. Key alphabet/length: generated keys match `[0-9A-Za-z]{6}`.

## Success criteria

All tests pass (`OK`, zero failures/errors) on a clean checkout with
only the Python 3 standard library. No test server is left running
after the suite: every server thread is shut down in `tearDown`.
