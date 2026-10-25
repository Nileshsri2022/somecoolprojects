# load-balancer — Design

## Assumptions (stated before coding, per ponytail)

1. Language: Python 3, standard library only, single
   file `lb.py`, same as the previous projects. `http.server`
   gives the threaded HTTP server; `http.client` gives
   the backend client. No third-party framework.
2. Threads, not asyncio. Reason: the challenge allows
   either, and threads keep the proxy code straight-line
   (forward, read response, return) while
   `ThreadingHTTPServer` handles concurrency.
3. Health state lives on `Backend` objects shared by the
   request threads and the health thread, guarded by one
   lock. Round-robin index and health flags are only
   ever touched under that lock, so picking a backend
   and marking it unhealthy cannot race.
4. Bodies are read fully before forwarding and read
   fully from the backend before responding. Reason:
   bodies in the challenge and tests are small; full
   buffering is far simpler than streaming, and the
   limitation is documented in SPEC.md.

## Components

```
Backend            host, port, origin string, healthy flag
Balancer           list of Backends, lock, round-robin index
  .next_healthy()  next healthy backend in rotation, or None
  .mark_unhealthy(backend) / .mark_healthy(backend)
  .health_check_once()   one GET per backend, update flags
  .health_loop(stop)     every interval, until stopped
Handler            BaseHTTPRequestHandler subclass
  .handle_request()      for GET/POST/PUT/DELETE/HEAD/PATCH
  .forward(backend)      http.client request, return response
  .send_error_response() 502 when no backend is healthy
make_server()      ThreadingHTTPServer + Balancer wiring
main()             argparse, initial health check, serve
```

## Request flow

```
client -> Handler.handle_request()
  body = read Content-Length bytes (if any)
  attempts = healthy backends, in round-robin order
  for backend in attempts:
      try: status, headers, body = forward(backend)
           break
      except (connection error, timeout):
           mark backend unhealthy, try next
  else: 502 Bad Gateway
  strip hop-by-hop headers from response
  send status + headers + body to client
  log: client IP, method, path, backend, status
```

`next_healthy()` advances the shared index past the
backend it returns, so consecutive requests rotate even
when some backends are unhealthy: it scans at most
`len(backends)` entries from the current index and
returns the first healthy one, with the index left
pointing after it.

## Health flow

```
health_loop: while not stopped:
    health_check_once()
    stopped.wait(interval)
health_check_once:
    for backend: GET backend.origin + health_path, timeout 2s
        200 -> mark healthy (logs a "back online" line
               only when the flag actually changes)
        else -> mark unhealthy (logs only on change)
```

An initial `health_check_once()` runs synchronously in
`main()` before serving, so a backend that is already
down never receives the first request — the first
health tick would otherwise be up to one interval away.
Flag-change-only logging keeps a healthy cluster quiet.

## File layout

```
load-balancer/
  README.md            usage, demo backends, how to run tests
  lb.py                balancer, handler, health loop, CLI
  docs/
    SPEC.md            challenge spec and behaviour
    DESIGN.md          this file
    TEST_PLAN.md       what is tested, and how
  tests/
    test_lb.py         unittest, live in-process backends
```

## Success criteria

- `python3 -m unittest discover -s tests -v` passes.
- Live tests (real sockets, ephemeral ports, no
  hard-coded ports): single-backend forwarding, strict
  round-robin alternation, POST body echo, health
  ejection and re-entry, 502 when all down, and 20
  concurrent requests all succeeding.
- Manual demo works: two `python -m http.server`
  backends, `curl` through the LB alternates.
