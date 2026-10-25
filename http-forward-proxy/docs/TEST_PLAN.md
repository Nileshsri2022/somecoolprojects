# TEST_PLAN — HTTP Forward Proxy Server

All tests use local servers on OS-assigned ephemeral ports.
No test proxies to an external website.

## Test harness

- A tiny origin server (stdlib `http.server`, threaded) records the
  last request it saw (method, path, headers, body) and serves
  canned bodies per path: `/hello` → `200 Hello, proxy!`,
  `/echo` → echoes method/path/body as JSON-ish text,
  `/secret` → body containing a banned word, `/binary` → bytes.
- The proxy under test is started in-process on an ephemeral port
  with explicit forbidden-host / banned-word lists (temp files).
- Clients are raw sockets (for absolute-form and CONNECT, where
  `http.client` hides the wire format) and `http.client` via a
  manual proxy request where convenient.
- Each test class starts its own proxy + origin and shuts them
  down in `tearDown`; ports are never hardcoded.

## Cases

Unit (no server):
1. `parse_request_target` — absolute http URL with port, path,
   query; absolute URL without port (→ 80); origin-form with Host
   header; CONNECT authority-form (host:port, default 443);
   missing host → ValueError; https absolute-form → ValueError;
   malformed line → ValueError.
2. `load_list_file` — comments/blank lines ignored, case folded,
   missing file → empty list.
3. `is_forbidden_host` — exact match, subdomain match,
   case-insensitivity, non-match, empty list.
4. `contains_banned_word` — case-insensitive substring, no match,
   empty list.
5. `strip_hop_by_hop_headers` — removes Proxy-Connection,
   Connection and headers named by Connection, keeps Host/User-Agent.

Integration (proxy + local origin):
6. GET absolute-form returns origin status, body, and a custom
   response header unchanged.
7. Origin-form GET (Host header only) is forwarded correctly.
8. POST with body: origin receives the same method, path, body,
   and a custom header; proxy adds `X-Forwarded-For` with the
   client IP and rewrites the target to origin form.
9. Hop-by-hop headers sent by the client are not forwarded.
10. Forbidden host (absolute-form) → 403, exact page body
    `Website not allowed: <host>`, and origin is never contacted.
11. Forbidden host via CONNECT → 403, no tunnel.
12. Banned word in response body → 403, body
    `Website content not allowed.`, origin body withheld.
13. Clean response with a non-empty banned list still passes through.
14. CONNECT tunnel: after `200 Connection Established`, a plain
    HTTP request sent through the tunnel reaches the origin and
    the response comes back through the tunnel.
15. Origin unreachable → 502.
16. Malformed request line → 400.
17. Logging: a request produces a log line containing method,
    target and status (captured via a log file).

## Manual checks (not in the suite, page examples)

- `curl --proxy http://127.0.0.1:8989 http://<local-origin>/hello`
- `curl --proxy http://127.0.0.1:8989 -v http://<forbidden>/`
  expecting the page's 403 output.
- `curl --proxy http://127.0.0.1:8989 https://<local-tls-or-tunnel>/`
  is covered in-test by the raw CONNECT case instead of real TLS,
  since tests must not depend on external sites or certificates.

## Run

```
python3 -m unittest discover -s tests -v
```
from the project directory.
