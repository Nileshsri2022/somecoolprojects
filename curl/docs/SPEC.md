# SPEC — Build Your Own curl (codingchallenges.fyi, `challenge-curl`)

Source page: https://codingchallenges.fyi/challenges/challenge-curl/
Slug used: `challenge-curl` — the first-guess slug, no correction needed
(verified live: the page title is "Build Your Own curl" and its steps
match the summary below). HTTP/1.1 as defined in RFC 9110, as the page
directs. The page's test site is httpbin; this build never depends on it
— all tests use a local HTTP server (see TEST_PLAN.md).

## Challenge steps, as written on the page

- Step 0: set up the project (language of choice).
- Step 1: parse the URL from the command line and print the protocol
  text for a GET request: protocol (checked, HTTP assumed at first),
  host, port (default 80 for HTTP), path. Example output:
  `Sending request GET /get HTTP/1.1`, `Host: eu.httpbin.org`,
  `Accept: */*`.
- Step 2: open a socket to the server on the specified port, send the
  Step 1 request (correct CRLF line termination), read the response
  and dump it. Send `Connection: close` so the server closes the
  connection after every request.
- Step 3: by default print only the response body; with verbose mode
  (`-v`) also print the request and response headers, prefixed `>`
  (sent) and `<` (received), e.g. `> GET /get HTTP/1.1`,
  `< HTTP/1.1 200 OK`.
- Step 4: `-X <method>` selects the HTTP method; DELETE is the
  worked example.
- Step 5: POST for RESTful APIs — `-d <string>` sends a data payload
  after the headers, `-H "Name: value"` adds a request header
  (worked example: `-H "Content-Type: application/json"`), and a
  `Content-Length` header states the payload length (RFC 9110 §8.6).
- Step 6: PUT, same shape as POST with a different method.
- Going Further (page's own list): HEAD and PATCH support, keep-alive
  / multiple requests over one connection, SSL (hence HTTPS).

## This implementation

```
python3 curl.py [options] URL
python3 curl.py -v http://localhost:PORT/get
python3 curl.py -X DELETE http://localhost:PORT/delete
python3 curl.py -X POST http://localhost:PORT/post \
    -d '{"key": "value"}' -H "Content-Type: application/json"
python3 curl.py -X PUT http://localhost:PORT/put \
    -d '{"key": "value2"}' -H "Content-Type: application/json"
```

Options (all page steps, plus the task's named extras):

| Option | Meaning |
| ------ | ------- |
| `-v`, `--verbose` | Step 3: print `>` request / `<` response headers to stderr |
| `-i`, `--include` | Print response status line + headers before the body on stdout (real-curl `-i` behaviour; the page's Step 2 dump, kept as an opt-in) |
| `-X`, `--request METHOD` | Step 4/6: HTTP method (GET, DELETE, POST, PUT, HEAD, PATCH, …); case-insensitive, sent upper-cased |
| `-d`, `--data DATA` | Step 5: request body string (UTF-8). Implies POST when no `-X` is given, as real curl does |
| `-H`, `--header "Name: Value"` | Step 5: extra request header; repeatable; later values replace earlier ones for the same name (case-insensitive) |
| `-o`, `--output FILE` | Write the body to FILE instead of stdout (status/verbose output is unaffected) |
| `-L`, `--location` | Follow redirects (see below) |
| `--max-redirs N` | Redirect limit for `-L` (default 10) |
| `-f`, `--fail` | Exit 22 and suppress the body when the final status is >= 400 |

Defaults per request: `Host` (host, plus `:port` only for a non-default
port), `Accept: */*`, `Connection: close`. `Content-Length` is added
automatically when a body is present and the user did not supply one
via `-H`. No `User-Agent` is sent by default (the page's examples send
none; see DESIGN.md).

## Behaviour rules

- URL: scheme must be `http` or `https` (default ports 80 / 443);
  anything else, a missing host, or a missing URL is a usage/URL
  error on stderr with a non-zero exit code. The path defaults to
  `/`; a query string is sent; a `#fragment` is never sent (it is
  client-side only, RFC 9110 §7.1).
- Body output is bytes: stdout is written via `sys.stdout.buffer`
  (or the `-o` file opened in binary mode), so binary bodies survive.
- Redirects (only with `-L`): follow 301, 302, 303, 307, 308 responses
  carrying a `Location` header, resolving relative locations against
  the current URL. 303 always becomes GET (body dropped) except HEAD,
  which stays HEAD; 301/302 turn a POST into GET (body dropped, the
  long-standing real-curl behaviour); 307/308 preserve method and
  body. Without `-L` a redirect response is printed as-is with exit
  code 0. Exceeding `--max-redirs` is an error (exit 47).
- Status handling: without `-f`, any completed response — including
  404/500 and un-followed redirects — prints its body and exits 0.
  With `-f`, a final status >= 400 prints an error to stderr, prints
  no body, and exits 22.
- Errors: connection refused / DNS failure / timeout / TLS failure /
  malformed URL / redirect overflow are reported on stderr with a
  curl-like exit code (see DESIGN.md) and no body output. Errors from
  writing the `-o` file are reported the same way.

## Out of scope (not on the page, not built)

- Keep-alive / connection reuse (page's Going Further #2): every
  request sends `Connection: close` and opens a fresh connection, as
  Steps 1–2 specify. Reuse is deliberately not implemented.
- Cookies, auth, proxies, FTP, multipart/form-data (`-F`), progress
  meters, globbing, config files: none of these appear on the page.
- HTTPS certificate verification is ON (default SSL context); there
  is no `-k`/insecure flag, by design.
