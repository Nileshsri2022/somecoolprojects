# curl — Build Your Own curl

Coding Challenges entry 37, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A curl clone for HTTP/1.1 REST-style requests (RFC 9110), Python 3
standard library only (`http.client` + `urllib.parse`). Implements
the challenge page's steps: URL parsing and request text (Step 1),
sending the request over a fresh `Connection: close` connection
(Step 2), body-only output with `-v` verbose headers (Step 3),
`-X` methods (Step 4), `-d` data + `-H` headers with
`Content-Length` (Step 5), PUT (Step 6), plus the page's Going
Further items HEAD/PATCH and HTTPS. Extensions beyond the page,
kept off by default: `-o` output file, `-L` redirects, `-f` fail
on HTTP errors, `-i` header dump.

## Usage

```sh
python3 curl.py http://localhost:8080/get
python3 curl.py -v http://localhost:8080/get
python3 curl.py -X DELETE http://localhost:8080/delete
python3 curl.py -X POST http://localhost:8080/post \
    -d '{"key": "value"}' -H "Content-Type: application/json"
python3 curl.py -X PUT http://localhost:8080/put \
    -d '{"key": "value2"}' -H "Content-Type: application/json"
python3 curl.py -L http://localhost:8080/redirect
python3 curl.py -o out.json http://localhost:8080/get
python3 curl.py -f http://localhost:8080/status/404  # exits 22
```

Default output is the response body only; `-v` prints `>` request
and `<` response headers to stderr, `-i` prints the response
status line and headers before the body. Without `-L`, redirect
responses are printed as-is; with `-L`, 301/302/303/307/308 are
followed (303 and POST-on-301/302 become GET; 307/308 keep method
and body), up to `--max-redirs 10`. Errors go to stderr with
curl-like exit codes (2 usage, 3 bad URL, 6 DNS, 7 connect, 22
`-f` failure, 23 output write, 47 redirect limit).

Divergences from real curl, by design: no `User-Agent` header by
default (the page's examples send none; add one with `-H` if you
want it), no keep-alive (every request sends `Connection: close`,
as Step 2 specifies), no `-k` flag (HTTPS certificates are always
verified), no cookies/auth/proxies/progress meter (not on the page).

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use only a local HTTP server on an ephemeral port — never
httpbin or any external site — covering URL parsing, headers,
GET/DELETE/POST/PUT/PATCH/HEAD, chunked bodies, redirect rules,
and CLI behaviour (`-v`, `-i`, `-o`, `-f`, error exit codes).
System curl 8.5.0 was spot-checked against the same local server
and agrees on method/headers/body for GET/POST/DELETE and `-L`
redirects, modulo the User-Agent / `Connection: close` divergences
above.

## Files

- `curl.py` — URL parsing, header building, request/redirect loop, CLI.
- `docs/SPEC.md` — challenge spec (slug `challenge-curl`) and behaviour rules.
- `docs/DESIGN.md` — assumptions, structure, exit codes, divergences.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_curl.py` — the test suite.
