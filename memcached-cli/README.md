# Memcached CLI Tool (Coding Challenges #18)

A command-line client for a Memcached server speaking the plain-text
protocol over TCP. Python 3, standard library only, single file.

**Note:** this is the client tool, distinct from the Memcached Server
project. It stores nothing itself — it talks to an already-running server.

## Usage

One-shot (one command per invocation):

```
python3 memcached_cli.py --host 127.0.0.1 --port 11211 set mykey myvalue
python3 memcached_cli.py --host 127.0.0.1 --port 11211 get mykey
python3 memcached_cli.py --host 127.0.0.1 --port 11211 get key1 key2
python3 memcached_cli.py --host 127.0.0.1 --port 11211 gets mykey
python3 memcached_cli.py --host 127.0.0.1 --port 11211 add mykey v --flags 0 --exptime 60
python3 memcached_cli.py --host 127.0.0.1 --port 11211 replace mykey newvalue
python3 memcached_cli.py --host 127.0.0.1 --port 11211 append mykey suffix
python3 memcached_cli.py --host 127.0.0.1 --port 11211 prepend mykey prefix
python3 memcached_cli.py --host 127.0.0.1 --port 11211 delete mykey
python3 memcached_cli.py --host 127.0.0.1 --port 11211 incr mykey 5
python3 memcached_cli.py --host 127.0.0.1 --port 11211 decr mykey
python3 memcached_cli.py --host 127.0.0.1 --port 11211 touch mykey 300
python3 memcached_cli.py --host 127.0.0.1 --port 11211 flush_all
python3 memcached_cli.py --host 127.0.0.1 --port 11211 stats
python3 memcached_cli.py --host 127.0.0.1 --port 11211 version
```

`--host` defaults to `localhost`, `--port` to `11211`, `--timeout` to `5`
seconds. The challenge page's form (`-host`/`-p`, as in
`ccmc -host localhost -p 11211 set testkey testvalue`) is also accepted.
Run with no subcommand to enter the interactive REPL:

```
python3 memcached_cli.py --host 127.0.0.1 --port 11211
memcached> set mykey myvalue
STORED
memcached> get mykey
mykey: myvalue
memcached> quit
```

In the REPL, `help` lists commands and `quit`/`exit`/Ctrl-D close the
connection. A `get` of a missing key prints nothing and is not an error.

## Docs

- `docs/SPEC.md` — challenge spec and protocol/output contract
- `docs/DESIGN.md` — assumptions and structure (written before coding)
- `docs/TEST_PLAN.md` — test approach and coverage

## Tests

```
python3 -m unittest discover -s tests -v
```

Tests run a small in-process fake Memcached server on an ephemeral port —
no real memcached daemon and no other project directory are needed.
