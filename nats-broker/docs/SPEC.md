# SPEC — NATS Message Broker (Coding Challenges, entry 26)

Source challenge page (read first, before coding):
https://codingchallenges.fyi/challenges/challenge-nats/
Slug used: `challenge-nats` — this was the first guess and it loaded
directly; no 404 correction was needed.

## What the page asks for

- Step 0: setup. Step 1: parse the NATS protocol (CONNECT, PING/PONG,
  SUB, PUB), TDD-style, e.g. `PING\r\n`, `SUB FOO 1\r\n`,
  `PUB CodingChallenge 11\r\nHello John!\r\n`.
- Step 2: server bones. Listen on port 4222. On connect, send an `INFO`
  message (host, port, client IP), accept `CONNECT {}` and reply `+OK`,
  reply `PONG` to `PING`.
- Step 3: SUB/PUB/MSG. SUB registers the client for a subject; PUB
  publishes a payload to all subscribers of that subject as
  `MSG <subject> <sid> <size>\r\n<payload>\r\n`. The page's example has
  the publisher also subscribed, and it receives its own message.
- Step 4: multiple concurrent clients (thread per client is acceptable).
- Step 5: UNSUB. After unsubscribing a client can still publish but no
  longer receives messages on that subject.

## Protocol implemented (core NATS, text protocol, CRLF-terminated)

Server sends on connect (before any client command):

```
INFO {"server_id":"...","version":"0.1.0","host":"127.0.0.1","port":4222,"client_ip":"127.0.0.1"}
```

Commands (all lines end `\r\n`; a bare `\n` is also tolerated):

| Command | Form | Reply |
|---|---|---|
| CONNECT | `CONNECT <json>` (empty options `{}` is fine) | `+OK`, or `-ERR 'Invalid CONNECT'` on bad JSON |
| PING | `PING` | `PONG` |
| PONG | `PONG` (client heartbeat reply) | none |
| SUB | `SUB <subject> [queue] <sid>` | `+OK` |
| UNSUB | `UNSUB <sid> [max_msgs]` | `+OK` |
| PUB | `PUB <subject> [reply-to] <size>` + `<size>` bytes + `\r\n` | `+OK`, then delivery |
| MSG (server→client) | `MSG <subject> <sid> [reply-to] <size>` + payload + `\r\n` | — |

Notes:

- `+OK` is sent for CONNECT/SUB/UNSUB/PUB. Real NATS only sends `+OK`
  in verbose mode; this server is verbose by default because the
  page's examples show `+OK` after every command. There is no
  verbose toggle.
- Unknown or malformed commands get `-ERR 'Unknown Protocol Operation'`
  (or a more specific `-ERR`); the connection stays open.
- PUB payloads are exactly `<size>` bytes, so payloads may contain
  CRLF or binary bytes. The trailing CRLF after a payload is consumed
  by the server and is not part of the payload.
- A client that disconnects has all its subscriptions removed.
- Subjects are dot-separated tokens, e.g. `coding.challenge`.
  Wildcards (standard NATS subject matching, an extension beyond the
  page's literal steps — the page links the NATS protocol docs, and
  the task brief asks for wildcards):
  - `*` matches exactly one token: `foo.*` matches `foo.bar`, not
    `foo.bar.baz`.
  - `>` matches one or more trailing tokens, and only as the final
    token: `foo.>` matches `foo.bar` and `foo.bar.baz`, not `foo`.
    (Real NATS also matches the bare prefix for `foo.>`; this server
    requires at least one token after the prefix — see Divergences.)
  - A `>` in a non-final position never matches.
- Queue groups: `SUB <subject> <queue> <sid>` joins a queue group.
  Each published message is delivered to exactly one member of each
  matching queue group (round-robin), and to every non-queue
  subscriber. This is standard NATS queue-group behaviour, included
  because the SUB form on the page says non-required fields may be
  ignored at first and queue is the standard optional field.
- UNSUB with `max_msgs`: the subscription is removed automatically
  after that many further deliveries. Plain `UNSUB <sid>` removes it
  at once. An unsubscribed client may still PUB.

## Deliberate divergences from the page / real NATS

1. Page Step 5 example shows `UNSUB 1-` after `SUB CC 10`. That is not
   valid NATS syntax (real syntax is `UNSUB <sid> [max_msgs]`), and
   the sid in the example is 10, so `1-` looks like a mis-rendering.
   This server implements standard `UNSUB <sid> [max_msgs]` only;
   `UNSUB 1-` is rejected with `-ERR`. Tests use `UNSUB 10`.
2. Default listen address is `127.0.0.1:4222` (page says port 4222);
   `--host`/`--port` override it, and tests use an ephemeral port
   (port 0) so no fixed port is needed.
3. `foo.>` requires at least one token after `foo.` (see above).
   Real NATS `foo.>` also matches bare `foo`.
4. No JetStream, persistence, clustering, authentication, TLS,
   WebSocket, monitoring port, or `nats bench` compatibility. Delivery
   is at-most-once, in-memory only: a restart loses subscriptions and
   any undelivered messages, and a message published with no
   subscribers is dropped.
5. INFO includes `server_id` and `version` in addition to the page's
   host/port/client_ip fields; extra JSON fields are harmless to
   clients that only read the fields they need.
6. Queue-group delivery is round-robin starting at the first member;
   real NATS load-balancing is not guaranteed to be round-robin.

## Run

```sh
python3 nats_broker.py                 # 127.0.0.1:4222
python3 nats_broker.py --host 127.0.0.1 --port 4223
```

Talk to it with telnet / netcat, or use the `NATSClient` class in
`nats_broker.py` (also usable from tests).
