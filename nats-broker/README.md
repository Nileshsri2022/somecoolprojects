# NATS Message Broker — Build Your Own NATS Message Broker (Coding Challenges #26)

A lite NATS server in Python 3 (standard library only): a threaded
TCP server speaking the core NATS text protocol — CONNECT, INFO,
PING/PONG, SUB/UNSUB, PUB/MSG — with subject wildcards (`*`, `>`)
and queue groups. Built from
https://codingchallenges.fyi/challenges/challenge-nats/

## Run

```sh
python3 nats_broker.py                 # listens on 127.0.0.1:4222
python3 nats_broker.py --host 127.0.0.1 --port 4223
```

Then talk to it with telnet:

```
% telnet localhost 4222
INFO {"server_id":"...","version":"0.1.0","host":"127.0.0.1","port":4222,"client_ip":"127.0.0.1"}
CONNECT {}
+OK
PING
PONG
SUB CC 10
+OK
PUB CC 4
JOHN
+OK
MSG CC 10 4
JOHN
```

Or use the minimal client in the same file:

```python
from nats_broker import NATSClient
c = NATSClient("127.0.0.1", 4222)
c.connect()
c.subscribe("foo.*", sid=1)
c.publish("foo.bar", b"hello")
subject, sid, reply, payload = c.read_msg(timeout=2.0)
```

## Commands

`CONNECT <json>`, `PING` → `PONG`, `SUB <subject> [queue] <sid>`,
`UNSUB <sid> [max_msgs]`, `PUB <subject> [reply-to] <size>` +
payload. Unknown commands get `-ERR` and the connection stays open.

Notes:

- `+OK` is sent after CONNECT/SUB/UNSUB/PUB (verbose by default,
  matching the page's transcripts).
- Delivery is in-memory, at-most-once, no persistence, no JetStream,
  no auth/TLS/clustering. See `docs/SPEC.md` for the full list of
  deliberate divergences — including the page's Step 5 example
  `UNSUB 1-`, which is not valid NATS syntax; this server implements
  standard `UNSUB <sid> [max_msgs]`.

## Tests

```sh
cd nats-broker
python3 -m unittest discover -s tests -v
```

Tests start the server on an ephemeral port and speak the raw
protocol plus the bundled client; no real NATS server is needed.

## Layout

- `nats_broker.py` — server, protocol handling, minimal client.
- `docs/SPEC.md` — challenge spec, protocol, divergences.
- `docs/DESIGN.md` — assumptions made before coding.
- `docs/TEST_PLAN.md` — what the tests cover.
- `tests/test_nats_broker.py` — unittest suite.
