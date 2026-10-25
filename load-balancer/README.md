# load-balancer — Build Your Own Load Balancer

Coding Challenges #5, worked one by one in
`somecoolprojects/`. Docs first, then code — see `docs/`.

Layer-7 HTTP load balancer: round robin over healthy
backends, background health checks, failover to the
next healthy backend when one dies mid-request.

## Usage

```sh
python3 lb.py --port 8000 \
  --backends http://127.0.0.1:8081 http://127.0.0.1:8082 \
  --health-path / --health-interval 10
```

Options: `--port` (default 8000), `--backends` (one or
more origins, required), `--health-path` (default `/`),
`--health-interval` seconds (default 10).

## Demo with the challenge's own backends

```sh
mkdir -p server8081 server8082
echo "Hello from the web server running on port 8081." > server8081/index.html
echo "Hello from the web server running on port 8082." > server8082/index.html
python3 -m http.server 8081 --directory server8081 &
python3 -m http.server 8082 --directory server8082 &
python3 lb.py --port 8000 \
  --backends http://127.0.0.1:8081 http://127.0.0.1:8082
curl http://localhost:8000/   # alternates 8081, 8082, ...
```

Kill one backend and requests go only to the other;
restart it and, after one health interval, rotation
resumes. If all backends are down, clients get 502.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests start real backends and a real LB on ephemeral
ports and check forwarding, round robin, POST bodies,
health ejection and re-entry, 502, and concurrency.

## Files

- `lb.py` — balancer, handler, health loop, CLI.
- `docs/SPEC.md` — challenge spec and behaviour.
- `docs/DESIGN.md` — components, request and health flow.
- `docs/TEST_PLAN.md` — test cases and timing notes.
- `tests/test_lb.py` — the test suite.
