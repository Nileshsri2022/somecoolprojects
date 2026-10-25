# SPEC — HTTP Forward Proxy Server

Source: https://codingchallenges.fyi/challenges/challenge-forward-proxy/
Slug used: `challenge-forward-proxy` (found by web search; the guess
`challenge-http-forward-proxy` was not tried because search returned the
exact URL first — no 404 correction was needed).

## Challenge summary (from the page, Steps 0–5)

Step 0: set up language/tooling; curl/Postman handy for manual testing.

Step 1 — minimal forward proxy, default port 8989 in the page's example:
`curl --proxy "http://localhost:8989" "http://httpbin.org/ip"`.
A proxied request arrives in absolute form, e.g.
`GET http://httpbin.org/ip HTTP/1.1` with `Host:` and
`Proxy-Connection: Keep-Alive`. The proxy must:
1. listen for connections;
2. parse the request to extract the target host;
3. open a new connection to the target;
4. forward the request minus hop-by-hop headers;
5. rewrite the absolute-form request target to origin form (`/ip`);
6. add an `X-Forwarded-For` header;
7. read the response and set the correct response headers;
8. send the response to the client.
The page's example log line: `Starting proxy server on 127.0.0.1:8989`
and `Request made. Target: httpbin.org:443 Client: 127.0.0.1:56157`.

Step 2 — forbidden hosts: read a list from `forbidden-hosts.txt` and
refuse requests for those hosts with `403 Forbidden`, e.g. body
`Website not allowed: facebook.com`, `Content-Type: text/plain;
charset=utf-8` and `X-Content-Type-Options: nosniff`.
(Divergence note: the page's example shows `Content-Length: 34`
for that body, but the body as printed is 33 bytes — 34 only with
a trailing newline. This implementation sends the exact length of
the body it sends, with no trailing newline.)

Step 3 — banned words: read a list from `banned-words.txt` and refuse
to serve a page if any banned word appears in the response, with
`403 Forbidden` and body `Website content not allowed.`
(Divergence note: the page's Step 3 example shows
`Content-Length: 43` next to that body, but the body as printed is
28 bytes. This implementation sends the correct length, 28, for the
body it actually sends.)

Step 4 — logging: log all traffic, to a file and optionally stdout,
including a date/timestamp (the page omits timestamps from its example
for clarity). Example shape from the page:
`Client: 127.0.0.1:62448 Request URL: http://httpbin.org/ip` followed
by `127.0.0.1:62448   200 OK`.

Step 5 — CONNECT tunnelling for HTTPS: support
`CONNECT httpbin.org:443 HTTP/1.1`; on a successful connection to the
target, reply `200` so a tunnel is established, then copy bytes in
both directions (including TLS traffic, which the proxy does not
inspect). Without this, curl reports
`CONNECT tunnel failed, response 400`.

Going Further (not required, not built): TLS on the client↔proxy leg,
and the warning that a TLS-terminating proxy can inspect traffic.
This implementation deliberately does NOT terminate TLS: CONNECT
tunnels are opaque byte pipes.

## Scope for this build

- Python 3 standard library only, single main file `proxy.py`.
- HTTP forwarding for any method (GET, POST, PUT, DELETE, HEAD, …),
  absolute-form and origin-form request targets, request bodies
  (Content-Length and chunked).
- CONNECT tunnelling (opaque, bidirectional).
- Forbidden-host refusal (HTTP and CONNECT) and banned-word refusal
  (HTTP responses only — tunnelled bytes are never inspected).
- Logging to stdout and optionally to a file.
- No caching, no authentication, no TLS termination, no gzip
  decompression (see DESIGN.md).

## Verifiable success criteria

1. `curl --proxy http://127.0.0.1:<port> http://<local-origin>/hello`
   returns the origin's body and status unchanged.
2. A POST with a body through the proxy reaches the origin intact
   (method, path, headers, body echoed back).
3. A request to a forbidden host returns 403 with the page's body.
4. A response containing a banned word returns 403 instead of the body.
5. `CONNECT <local-origin>` followed by a plain HTTP request through
   the tunnel returns the origin's response.
6. `python3 -m unittest discover -s tests -v` passes fully, using
   only local origin servers on ephemeral ports (no external sites).
