# Redis CLI — Spec

Source challenge page (read first, 2026-10-25):
https://codingchallenges.fyi/challenges/challenge-redis-cli/
Slug used: `challenge-redis-cli`. No correction needed — the first-guess
URL returned the full page (Steps 0–5 + Going Further). Note: the page's
rendered RESP type bytes for Errors and Arrays are blank in the fetched
text; the RESP specification values (`-` for errors, `*` for arrays) are
used, matching the Redis server project in this repo and the page's own
examples (`*1\r\n$4\r\nping\r\n`, `+OK\r\n`, `$-1\r\n`).

## Step 1 — RESP serialisation / deserialisation (RESP2)

- Clients send commands as a RESP Array of Bulk Strings, e.g.
  `*2\r\n$3\r\nget\r\n$3\r\nkey\r\n`.
- Server replies are one of: Simple String (`+`), Error (`-`), Integer
  (`:`), Bulk String (`$`, `$-1\r\n` = null), Array (`*`, `*-1\r\n` =
  null, elements may nest).
- Page's TDD examples (all covered by tests, plus invalid cases):
  `$-1\r\n`, `*1\r\n$4\r\nping\r\n`, `*2\r\n$4\r\necho\r\n$11\r\nhello
  world\r\n`, `*2\r\n$3\r\nget\r\n$3\r\nkey\r\n`,
  `*3\r\n$3\r\nset\r\n$3\r\nkey\r\n$5\r\nvalue\r\n`, `+OK\r\n`,
  `-Error message\r\n`, `$0\r\n\r\n`, `+hello world\r\n`.

## Step 2 — One-shot mode

`redis_cli.py PING` connects, sends PING, prints the decoded reply
(`PONG`), closes. Any command works one-shot, not just PING:
`redis_cli.py SET key value`, `redis_cli.py GET key`, etc. Arguments are
taken verbatim from the shell (no extra quoting layer).

## Step 3 — Host/port options and REPL

```
redis_cli.py --host localhost -p 6379
redis_cli.py --host 127.0.0.1 --port 6380
```

Defaults: host `localhost`, port `6379`, timeout 5 s. One divergence
from the page's spelling: the page writes `-h localhost`, but `-h` is
argparse's built-in help flag, so this build takes `--host` (and
`-host` as an alias, as in the sibling memcached-cli project) plus
`-p`/`--port`; see DESIGN.md. With no command arguments the tool enters a
REPL whose prompt shows host and port, exactly as on the page:

```
127.0.0.1:6379> ping
PONG
127.0.0.1:6379> ping Hello
Hello
127.0.0.1:6379> quit
```

`quit` (and `exit`) are handled client-side: never sent to the server,
connection closed, program exits. Ctrl-D / Ctrl-C also exit cleanly.
REPL input is split with `shlex`, so `set k "hello world"` sends one
value argument. An empty line is ignored.

## Step 4 — Help (client-side, no server round-trip)

- `help` prints the page's intro text: how to ask for `help @<group>`,
  `help <command>`, and that `quit` exits.
- `help <command>` prints `usage`, `summary`, `since`, `group` for that
  command, in the page's layout.
- `help @<group>` lists the known commands in that group.
- Unknown command/group prints an error line, not a server round-trip.

The page says to take help content from the Redis repo's
`redis/src/commands` JSON files. This build embeds a curated subset
covering the commands this CLI is specified to exercise (see
Divergences); it does not fetch or vendor the full JSON set.

## Step 5 — Hints

Full as-you-type inline hints (the screenshot on the page) need a
terminal UI that renders a ghost hint while typing; stdlib line input
cannot do that. Implemented instead: in the REPL, entering a known
command that requires arguments but giving none prints that command's
usage hint instead of sending a doomed request (e.g. bare `get` prints
the GET usage). `help <command>` is the full hint source at any time.
See Divergences.

## Going Further — file of commands

Not implemented (optional on the page; minimum-code rule). Documented
here so a later addition has a defined shape: one command per line,
run in turn, stop on first error reply.

## Commands exercised

The CLI itself is command-agnostic: it sends whatever the user typed
as a RESP array, so any server command works (PING, ECHO, SET, GET,
DEL, EXISTS, INCR, DECR, LPUSH, RPUSH, LRANGE, LLEN, ...). The help
table and the tests cover: PING, ECHO, SET, GET, DEL, EXISTS, INCR,
DECR, LPUSH, RPUSH, LRANGE, LLEN. The fake server in the tests
implements the same set (plus PING-with-message) so behaviour is
checked end to end.

## Reply formatting (redis-cli style)

- Simple string / bulk string: printed raw (`PONG`, `value`).
- Null bulk / null array: `(nil)`.
- Integer: `(integer) 3`.
- Error: `(error) <message>`.
- Array: one element per line, numbered `1) ...`, `2) ...`; empty
  array prints `(empty array)`; nested arrays are indented two spaces
  per level with their own numbering.
- Bytes that are not valid UTF-8 are decoded with replacement
  characters rather than crashing.

## Exit codes

- `0`: command(s) ran; an error *reply* from the server is still exit
  0 (the server answered).
- `1`: connection failure, protocol error, or bad CLI usage
  (message on stderr).

## Divergences from the page (deliberate, minimal)

1. Bare invocation enters the REPL instead of Step 2's PING-and-exit.
   Rationale: the task for this project specifies both one-shot and
   REPL modes; `redis_cli.py PING` is the Step 2 behaviour exactly.
2. Help content is an embedded curated subset, not the full Redis
   commands JSON set (Step 4, partial).
3. Hints are bare-command usage hints in the REPL, not inline
   as-you-type ghost text (Step 5, partial — see above).
4. RESP2 only; RESP3 types (`%` maps, `_` null, `#` booleans, etc.)
   are rejected as protocol errors. The page only specifies RESP2.
5. No `--file` batch mode (page's Going Further, optional).
6. Prompt shows the host exactly as given (`localhost:6379`), not a
   resolved IP; the page's example shows `127.0.0.1:6379` when that
   host was passed.
7. `-h` is argparse help, not host: use `--host`/`-host` (see Step 3
   and DESIGN.md). `-p`/`--port` work as on the page.
