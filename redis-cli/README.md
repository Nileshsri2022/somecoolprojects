# Redis CLI Tool (Coding Challenges #52)

A command-line client for a Redis server speaking RESP2 over TCP.
Python 3, standard library only, single file. Built from
https://codingchallenges.fyi/challenges/challenge-redis-cli/ (slug:
`challenge-redis-cli`).

**Note:** this is the client tool, distinct from the Redis Server
project. It stores nothing itself — it talks to an already-running
server, and sends any command verbatim as a RESP array, so commands
beyond the help table work too.

## Usage

One-shot (one command per invocation):

```
python3 redis_cli.py --host 127.0.0.1 -p 6379 PING
python3 redis_cli.py --host 127.0.0.1 -p 6379 SET key value
python3 redis_cli.py --host 127.0.0.1 -p 6379 GET key
python3 redis_cli.py --host 127.0.0.1 -p 6379 DEL key
python3 redis_cli.py --host 127.0.0.1 -p 6379 EXISTS key
python3 redis_cli.py --host 127.0.0.1 -p 6379 INCR counter
python3 redis_cli.py --host 127.0.0.1 -p 6379 DECR counter
python3 redis_cli.py --host 127.0.0.1 -p 6379 RPUSH mylist a b
python3 redis_cli.py --host 127.0.0.1 -p 6379 LRANGE mylist 0 -1
```

`--host` defaults to `localhost`, `-p`/`--port` to `6379`,
`--timeout` to `5` seconds. The `-host` spelling is also accepted.
Note: `-h` is this tool's `--help` flag (argparse), so the page's
`-h localhost` form is written here as `--host localhost` — see
`docs/SPEC.md` for the full list of divergences.

Run with no command to enter the interactive REPL:

```
python3 redis_cli.py --host 127.0.0.1 -p 6379
127.0.0.1:6379> ping
PONG
127.0.0.1:6379> set key value
OK
127.0.0.1:6379> get key
value
127.0.0.1:6379> help set
  SET key value [NX|XX] [GET] [EX seconds|PX milliseconds|EXAT unix-time-seconds|PXAT unix-time-milliseconds|KEEPTTL]
  summary: Set the string value of a key
  since: 1.0.0
  group: string
127.0.0.1:6379> quit
```

In the REPL, `help` lists how to get help, `help <command>` and
`help @<group>` show usage, and `quit`/`exit`/Ctrl-D close the
connection without sending anything. A bare command that needs
arguments (e.g. `get` alone) prints its usage hint instead of
sending a doomed request. REPL input honours shell-style quoting:
`set k "hello world"` sends one value. Replies print redis-cli
style: raw strings, `(nil)`, `(integer) N`, `(error) ...`, numbered
arrays, `(empty array)`.

Exit codes: `0` when the server answered (even with an error
reply), `1` on connection failure, protocol error, or bad usage.

## Docs

- `docs/SPEC.md` — challenge spec, reply formatting, divergences
- `docs/DESIGN.md` — assumptions and structure (written before coding)
- `docs/TEST_PLAN.md` — test approach and coverage

## Tests

```
python3 -m unittest discover -s tests -v
```

Tests run a small in-process fake Redis server on an ephemeral port
— no real Redis daemon and no other project directory are needed.
The in-repo `redis-server` project was used only as a manual,
read-only oracle (PING, SET/GET, INCR, RPUSH/LRANGE, REPL all
verified against it); it was not modified.
