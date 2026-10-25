# DESIGN — HTTP Forward Proxy Server

## Assumptions (stated before coding, per ponytail rules)

- One request per client connection for plain HTTP, except CONNECT
  tunnels, which stay open until either side closes. The proxy tells
  both client and origin `Connection: close`, so neither side needs
  keep-alive bookkeeping. This is the smallest design that satisfies
  the page; curl and `http.client` both cope with it.
- The proxy is a raw-socket server (`socketserver.ThreadingMixIn`),
  not `http.server`, because CONNECT tunnelling needs raw byte
  copying after the 200 reply, which a request/response handler
  framework fights.
- Targets are taken from the request line first, falling back to the
  `Host:` header for origin-form requests. Default ports: 80 for
  `http:`, 443 for CONNECT (and for any authority without a port).
- Only `http` absolute-form URLs are forwarded as HTTP. An
  `https://…` absolute-form target (without CONNECT) is rejected
  with 400 — the correct client behaviour for HTTPS is CONNECT
  (Step 5), and silently downgrading it to plain HTTP would be wrong.
- Forbidden-host matching is case-insensitive and matches a host
  exactly or as a subdomain of a listed entry (`www.facebook.com`
  matches `facebook.com`). Entries are one host per line; blank
  lines and `#` comments are ignored.
- Banned-word matching is a case-insensitive substring search over
  the raw response body. The proxy forces `Accept-Encoding: identity`
  on forwarded requests so origins do not gzip the body and hide
  words from the check (documented limitation: a body that is
  gzipped anyway, e.g. an origin ignoring the header, is checked
  as raw bytes and may slip through; the proxy never decompresses).
- Hop-by-hop headers stripped (RFC 7230 §6.1): `Connection`,
  `Keep-Alive`, `Proxy-Connection`, `TE`, `Trailer`,
  `Proxy-Authorization`, `Proxy-Authenticate`, `Upgrade`, plus any
  header names listed in the incoming `Connection:` value, plus
  `Transfer-Encoding` on the relayed side (bodies are de-chunked and
  re-sent with `Content-Length`).
- `X-Forwarded-For` is appended to any existing value, using the
  client's IP address.
- Errors: malformed request line / missing host → 400; origin
  unreachable → 502; forbidden host → 403; banned content → 403;
  CONNECT to a forbidden host → 403; CONNECT failure → 502.
  Error bodies are plain text, matching the page's style.

## Request flow (plain HTTP)

```
client ── request line + headers + body ──> proxy
proxy: parse target, check forbidden list, strip hop-by-hop,
       rewrite absolute-form → origin-form, add X-Forwarded-For,
       force Accept-Encoding: identity, Connection: close
proxy ── origin-form request ──> origin (new TCP connection)
origin ── status + headers + body ──> proxy
proxy: strip hop-by-hop, de-chunk if needed, check banned words
       (HEAD: no body is read or checked)
proxy ── status + headers + body ──> client, then close
```

Response bodies are read fully before relaying. That is what makes
the banned-word check possible (the page's Step 3 requires refusing
the whole page, not truncating mid-body). It costs memory on huge
bodies — accepted, and noted as a limitation for a production proxy.

## CONNECT flow

```
client ── CONNECT host:port ──> proxy ── connect ──> origin
proxy ── "HTTP/1.1 200 Connection Established" ──> client
proxy: select() loop copying bytes both ways until EOF/error
```

No header or body inspection happens inside the tunnel, so banned
words and forbidden-body checks do not apply — but the forbidden-host
check does apply to the CONNECT target itself, before tunnelling.

## Logging

Each request logs one line to stdout (and to `--log-file` if given):
`YYYY-MM-DD HH:MM:SS <client-ip>:<port> <METHOD> <target> <status>`
plus the page-style `Starting proxy server on <host>:<port>` line at
startup. Logging never blocks forwarding; a failed log write is
ignored.

## CLI

```
python3 proxy.py [--host 127.0.0.1] [--port 8989]
                 [--forbidden-hosts forbidden-hosts.txt]
                 [--banned-words banned-words.txt]
                 [--log-file proxy.log]
```

`--forbidden-hosts` / `--banned-words` accept a path, or the word
`none` to disable that list. If a path is given but the file does
not exist, the list is empty (with a warning on stderr) rather than
a fatal error — a missing optional blocklist should not kill the
proxy. The shipped `forbidden-hosts.txt` / `banned-words.txt` are
comment-only, i.e. empty lists, so the default run is unfiltered.

## Files

- `proxy.py` — server, handler, parsers, CLI. Importable helpers
  (`parse_request_target`, `load_list_file`, `is_forbidden_host`,
  `contains_banned_word`, `strip_hop_by_hop_headers`,
  `create_proxy_server`) exist so tests can unit-test them without
  starting a server.
- `forbidden-hosts.txt`, `banned-words.txt` — sample blocklists.
- `docs/` — this design, SPEC, TEST_PLAN.
- `tests/test_proxy.py` — unittest suite (local servers only).

## What is NOT built (deliberate, minimal scope)

- Caching, auth, TLS termination, HTTP/2, WebSocket upgrade,
  keep-alive reuse, gzip decompression, chunked streaming relay
  (bodies are buffered for the banned-word check).
