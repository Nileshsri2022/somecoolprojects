# DESIGN — curl clone

## Assumptions (stated before coding, ponytail rule)

1. Python 3 standard library only. Network layer is `http.client`
   (`HTTPConnection` / `HTTPSConnection`), not raw sockets and not
   `urllib.request`: `http.client` gives exact control of the request
   line and headers (matching the page's Step 1/2 "print the protocol
   text, then send it") while still handling chunked responses and
   content-length framing, which hand-rolled socket reading gets
   wrong. `urllib.parse` handles URL splitting only.
2. One request = one connection. `Connection: close` is always sent
   (page Step 2); no keep-alive, no pooling.
3. The page's Step 1/2 output (request text, full response dump) is
   verbose/debug output, not default output: Step 3 explicitly makes
   headers verbose-only. So default output is body-only; `-v` prints
   `>`/`<` lines to stderr (real curl puts verbose output on stderr,
   so stdout stays clean for piping); `-i` restores the Step 2-style
   header dump on stdout for users who want it.
4. `-o`, redirects and `-f` are extensions beyond the page's numbered
   steps (named in the build brief, standard curl behaviour). They
   are kept small, documented in SPEC.md, and never change the
   default (no-redirect, no-fail, stdout) behaviour.
5. Header casing: sent as the user wrote them for `-H` headers, and
   in the page's casing (`Host`, `Accept`, `Connection`,
   `Content-Length`) for built-ins. Matching is case-insensitive.

## Structure (`curl.py`, single file)

- `parse_url(url)` -> `ParsedUrl(scheme, host, port, target)`:
  `urllib.parse.urlsplit`; rejects empty URL, missing scheme/host,
  non-http(s) scheme, and non-numeric/out-of-range ports. Default
  ports 80/443. `target` = path or `/`, plus `?query` if present;
  fragment dropped. Raises `CurlError(code, message)`.
- `build_headers(parsed, method, body, extra_headers)` -> ordered
  list of `(name, value)`: `Host` (with `:port` iff non-default),
  `Accept: */*`, `Connection: close`, then user `-H` headers in
  order (a user header with the same name, case-insensitive, replaces
  the built-in — so `-H "Accept: application/json"` works), then
  `Content-Length` iff body is present and not user-supplied.
  A `-H` value without `:` is an error (real curl rejects it too).
- `send_once(parsed, method, headers, body, verbose)` -> `Response`:
  opens `HTTPConnection`/`HTTPSConnection` (HTTPS with the default,
  verifying SSL context), and calls `putrequest(..., skip_host=True,
  skip_accept_encoding=True)` so `http.client` does not inject its
  own `Host`/`Accept-Encoding: identity` headers — the wire headers
  are exactly the ones `build_headers` produced, i.e. exactly the
  page's Step 1 text plus `Connection: close`. Sends body bytes if
  any, reads the full response (`resp.read()` handles chunked and
  length-framed bodies). Verbose lines are written to stderr as the
  request/response are produced. Returns `Response(status, reason,
  headers, body)`; headers kept as a list of pairs (duplicates and
  order preserved) plus a case-insensitive lookup helper.
- `request(url, ...)` -> `Response`: the redirect loop. Repeatedly
  calls `send_once` while `-L` is on, the status is 301/302/303/
  307/308, and a `Location` header exists; resolves it with
  `urllib.parse.urljoin`; applies the method/body rewrite rules in
  SPEC.md; counts hops and raises `CurlError(47, ...)` past
  `--max-redirs`. Connection errors are wrapped as `CurlError`
  (see exit codes) instead of leaking `http.client`/`socket`
  tracebacks.
- `main(argv)` -> exit code: hand-rolled argument parsing (not
  `argparse` — see below), calls `request`, applies `-f`, writes
  the body to stdout-buffer or the `-o` file, prints `-i` headers
  before the body. `CurlError` and `BrokenPipeError` are caught and
  reported on stderr.

## Why hand-rolled argument parsing, not argparse

`argparse` prints its own usage/errors and exits 2, and it happily
accepts `--request=POST` and abbreviations that real curl does not.
The CLI surface here is tiny (9 flags); a short explicit parser
keeps error messages in curl's voice (`curl: (3) URL rejected...`,
`curl: option -H: requires a value`) and lets exit codes follow
curl's conventions exactly. This is a deliberate, minimal choice,
not a framework avoidance habit.

## Exit codes (curl-compatible where the situation maps)

| Code | Situation |
| ---- | --------- |
| 0 | Request completed (any status, unless `-f` tripped) |
| 2 | CLI usage error (unknown option, missing option value, no URL, extra operands) |
| 3 | Malformed URL / unsupported scheme / bad `-H` / bad `--max-redirs` |
| 6 | DNS resolution failure |
| 7 | Connection refused / timeout / TLS failure |
| 22 | `-f` and final status >= 400 |
| 23 | Cannot write the `-o` file |
| 47 | Redirect limit exceeded |

Anything else unexpected is exit 1. `socket.gaierror` maps to 6;
`ConnectionRefusedError`/`TimeoutError`/`ssl.SSLError`/`OSError`
during connect/send map to 7.

## Divergences from real curl (documented, deliberate)

- No `User-Agent` header by default (page examples send none).
  Real curl sends `User-Agent: curl/<version>`. A user can add one
  with `-H "User-Agent: ..."`.
- Verbose output uses the page's `>`/`<` prefix format and goes to
  stderr; real curl's `-v` format is similar but includes extra
  `*` connection lines, which this clone omits.
- `-d` with `-X GET` sends the body with GET (real curl does the
  same when both are given explicitly). `-d` alone implies POST.
- No progress meter, no globbing, no cookies: not on the page.
- Redirects are off by default, as in real curl; `-L` enables them.
- HTTPS works via `http.client.HTTPSConnection` (page Going Further
  #3) but there is no `-k` flag: verification cannot be disabled.

## Success criteria (verifiable)

`python3 -m unittest discover -s tests -v` passes against a local
server only; manual spot-checks against system curl (8.5.0) on the
same local server agree on status line, echoed method/headers/body
for GET/DELETE/POST/PUT/PATCH/HEAD, redirect chains, and `-o` output.
