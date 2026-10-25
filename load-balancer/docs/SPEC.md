# load-balancer — Specification (docs first)

Source: Coding Challenges, "Build You Own Load Balancer"
(https://codingchallenges.fyi/challenges/challenge-load-balancer/)
Target in this repo: `somecoolprojects/load-balancer/`

A layer-7 (application) load balancer: it sits in front of
a pool of HTTP servers and routes client requests across
the servers that can fulfil them, so no server is
overloaded, and a server going offline stops receiving
traffic until it comes back.

## Challenge steps

1. Start up, listen on a port, log the incoming request,
   forward it to a single backend, pass the response back.
   Test backend replies `Hello From Backend Server`, and
   the LB logs `Response from server: HTTP/1.1 200 OK`.
   Concurrency is required: multiple clients at once,
   via threads or async.
2. Round robin over two or more backends: with three
   servers and six requests, A gets 1 and 4, B gets 2
   and 5, C gets 3 and 6. Backends are listed on the
   command line (or hard-coded at first — this tool uses
   the command line from the start).
3. Health checks, in the background, concurrently with
   request handling:
   - Periodically GET a health-check URL (configurable
     period — 10 seconds suggested for manual testing —
     and configurable URL).
   - Status 200 = healthy; anything else = unhealthy,
     stop sending it requests.
   - When a health check starts passing again, add the
     server back.
   - Manual test: 3 backends, verify rotation, kill one,
     verify requests go only to the remaining two with
     no client errors, restart it, wait longer than the
     health period, verify it serves again.
   - Final test: concurrent clients (e.g. `curl
     --parallel`) all succeed.

## Commands

```
python3 lb.py --port 8000 \
  --backends http://127.0.0.1:8081 http://127.0.0.1:8082 \
  [--health-path /] [--health-interval 10]
```

Backends are also demoable with the challenge's own
suggestion:

```
mkdir -p server8081 server8082
echo "Hello from the web server running on port 8081." > server8081/index.html
echo "Hello from the web server running on port 8082." > server8082/index.html
python3 -m http.server 8081 --directory server8081
python3 -m http.server 8082 --directory server8082
curl http://localhost:8000/   # alternates between the two
```

## Behaviour

- Method, path, query string, headers and body are
  forwarded to the chosen backend; status, headers and
  body come back to the client.
- Hop-by-hop headers (`Connection`, `Keep-Alive`,
  `Transfer-Encoding`, `TE`, `Trailer`,
  `Proxy-Connection`, `Upgrade`) are stripped in both
  directions. `Host` is set to the backend, and
  `X-Forwarded-For` (client IP, appended) and
  `X-Forwarded-Proto: http` are added.
- Round robin: each request goes to the next healthy
  backend in list order, wrapping around.
- Health: a background thread GETs
  `<backend><health-path>` every interval. Only a 200
  counts as healthy. Any connection error, timeout, or
  non-200 marks the backend unhealthy.
- Failover on proxy error: if the chosen backend fails
  mid-request (e.g. it died since its last health
  check), it is marked unhealthy immediately and the
  request is retried on the next healthy backend, so
  the client does not see an error while any backend
  is alive. If no backend is healthy, the client gets
  `502 Bad Gateway` with a plain-text explanation.
- Logging to stdout, per request: client IP, method,
  path, chosen backend, backend status, and the same
  `Response from server: HTTP/1.1 <status>` line the
  challenge shows in step 1.

## Out of scope (ponytail: challenge steps only)

- No least-connections, no IP-hash / sticky routing, no
  weighted round robin. Those are extensions, not steps.
  (A separate, earlier load-balancer build explored
  them; this project is the challenge's round-robin
  version, built fresh and smaller.)
- No TLS termination, no HTTP/2, no keep-alive reuse of
  backend connections (one connection per forwarded
  request), no request streaming for chunked bodies:
  bodies are forwarded by `Content-Length` only.
- No dynamic backend add/remove API: the backend list
  is fixed at startup. A backend "coming back" means
  its health check passing again, not being re-added.
