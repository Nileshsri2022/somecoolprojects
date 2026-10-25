# Redis Server — Build Your Own Redis Server (Coding Challenges #8)

A lite Redis in Python 3 (standard library only): a threaded TCP server
speaking RESP, with strings, lists, key expiry, and snapshot
persistence. Built from https://codingchallenges.fyi/challenges/challenge-redis/

## Commands

`PING [message]`, `ECHO message`, `SET key value [EX seconds | PX ms |
EXAT unix-seconds | PXAT unix-ms]`, `GET key`, `EXISTS key...`,
`DEL key...`, `INCR key`, `DECR key`, `LPUSH key element...`,
`RPUSH key element...`, `LRANGE key start stop` (extra, so list
contents are observable — see `docs/SPEC.md`), `SAVE`.

## Run

```sh
python3 redis_server.py            # listens on 127.0.0.1:6379
python3 redis_server.py --port 6380 --host 127.0.0.1
python3 redis_server.py --dump-file /path/to/dump.rdb
```

Then talk to it with `redis-cli` (if installed), e.g.
`redis-cli -p 6379 PING`, or any RESP client.

Notes:

- The dump file format is a JSON snapshot, **not** real Redis RDB
  format — it is loadable by this server only. See `docs/SPEC.md`
  for the full list of deliberate divergences.
- Expiry is lazy (checked on access); see `docs/SPEC.md`.

## Tests

```sh
cd redis-server
python3 -m unittest discover -s tests -v
```

Tests start the server on an ephemeral port and speak raw RESP over
sockets; no real Redis or hard-coded port is needed.

## Layout

- `redis_server.py` — the server (RESP codec, store, dispatcher, TCP plumbing).
- `docs/SPEC.md` — challenge spec, RESP, divergences.
- `docs/DESIGN.md` — assumptions made before coding.
- `docs/TEST_PLAN.md` — what the tests cover.
- `tests/test_redis_server.py` — unittest suite.
