# Memcached Server — Coding Challenges #17

A single-node, in-memory Memcached server speaking the Memcached text
protocol over TCP. Python 3 standard library only.

Challenge page: https://codingchallenges.fyi/challenges/challenge-memcached/

## Run

```sh
python3 memcached_server.py            # listens on 127.0.0.1:11211
python3 memcached_server.py -p 9999    # listens on 127.0.0.1:9999
```

Then talk to it (e.g. with telnet, or `nc`):

```
set test 0 0 4
1234
STORED
get test
VALUE test 0 4
1234
END
```

## Supported commands

`set`, `add`, `replace`, `append`, `prepend`, `get` (single or
multi-key), `delete` — all with `flags`, `exptime` (lazy expiration),
byte-counted data blocks, and `noreply`. See `docs/SPEC.md` for the
full spec and `docs/DESIGN.md` for design assumptions.

Deliberately not implemented (the page's "Going Further" options):
`cas`, `incr`/`decr`, cache-size limits/eviction, the binary protocol,
persistence.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests start the real server on an ephemeral port and speak the wire
protocol over raw sockets. See `docs/TEST_PLAN.md` for the case list.

## Layout

```
memcached_server.py          # the server (single file)
docs/SPEC.md                 # challenge spec, as implemented
docs/DESIGN.md               # assumptions made before coding
docs/TEST_PLAN.md            # test plan
tests/test_memcached_server.py
README.md
```
