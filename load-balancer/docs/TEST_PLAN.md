# load-balancer — Test plan

Run: `python3 -m unittest discover -s tests -v` from
`load-balancer/`.

Tests are live: they start real backend HTTP servers and
a real LB on ephemeral ports (port 0, then read the
assigned port), make real HTTP requests with
`urllib.request`, and shut everything down in tearDown.
No hard-coded ports, so tests do not clash with a
developer's own servers.

## Helpers

- `make_backend(name)`: a `ThreadingHTTPServer` whose
  handler replies `Hello from backend <name>` to GET `/`
  (and any path), echoes the request body back on POST,
  and returns 200 on the health path. Each backend runs
  in its own daemon thread.
- `make_lb(backends, interval)`: a `lb` server on an
  ephemeral port, health interval short (0.2 s) so
  ejection/re-entry tests do not wait 10 seconds.
- `get(url)`: urllib GET, returns (status, body).
  A 502 is returned, not raised, by catching
  `urllib.error.HTTPError`.

## Cases

- Single backend: GET through the LB returns exactly
  that backend's body and status 200.
- Round robin: 6 GETs over 2 backends return
  A, B, A, B, A, B in order.
- POST body: a POST with a body through the LB returns
  the same body (backend echo), proving bodies forward.
- Picker unit test (no sockets): `next_healthy()` over
  [A, B, C] with B marked unhealthy returns A, C, A, C.
- Health ejection: 2 backends, verify alternation,
  shut backend B down, wait for at least two health
  ticks, verify all requests now go to A only.
- Health re-entry: restart a backend on the same port
  (new server object, same origin), wait for ticks,
  verify alternation resumes.
- All down: both backends shut down, wait for ticks,
  GET returns 502 (not a hang, not a traceback to the
  client).
- Concurrency: 20 parallel GETs (ThreadPoolExecutor)
  over 2 backends, all status 200, both backends
  served at least one request.

## Timing notes

Health tests poll: after shutting a backend down, they
wait in small steps until the LB's view changes (or a
3-second timeout), rather than sleeping a fixed amount
and hoping. The health interval in tests is 0.2 s, so
the waits are short in practice.

## What is NOT tested

- The challenge's Dropbox backend content and the
  `curl --parallel` manual test: the live tests cover
  the same properties (rotation, failover, concurrency)
  with in-process backends.
- TLS, HTTP/2, chunked request bodies, keep-alive
  backend reuse: out of scope, see SPEC.md.
