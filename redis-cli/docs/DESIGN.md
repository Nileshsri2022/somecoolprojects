# Redis CLI — Design (written before code)

## Assumptions (stated up front, ponytail rule)

1. The CLI is a dumb RESP pipe with two client-side exceptions:
   `help`/`quit`/`exit` never reach the server. Everything else is
   sent verbatim as an array of bulk strings. This is the smallest
   design that satisfies every page step: no per-command client logic
   to rot, and new server commands work with zero CLI changes.
2. Text, not bytes, at the edges: command arguments are `str` from
   argv / REPL input, encoded UTF-8 for the wire; replies are decoded
   UTF-8 with `errors="replace"`. Binary-safe bulk strings are out of
   scope (the page never requires them).
3. One TCP connection per invocation in one-shot mode; one connection
   for the whole REPL session. No pipelining, no reconnect, no auth
   (no AUTH/SELECT on the page).
4. `localhost` stays `localhost` in the prompt (no DNS resolution for
   display); the socket layer resolves it as usual.
5. Tests must not need a real Redis daemon or a fixed port: a fake
   server in the test process, bound to port 0, serves RESP for the
   covered commands. The in-repo `redis-server` project may be used
   as a read-only oracle by hand, never modified, never imported by
   the tests (importing it would couple the suites).

## Structure (single file, stdlib only)

`redis_cli.py`:

- `RespError(ValueError)` / `RedisError(Exception)` — protocol
  failures vs. server error replies carried as values.
- `encode_command(args)` — `list[str]` -> RESP array bytes. Pure,
  unit-testable without a socket.
- `RespReader` — buffered reader over a socket (or any object with
  `recv`); `read_reply()` parses one RESP value recursively and
  returns `str | int | list | None | RedisError`. Raises `RespError`
  on truncation, unknown prefix, malformed length, or a bulk/array
  body that ends early. A `parse_reply_bytes(data)` helper wraps it
  over a bytes buffer for the page's TDD examples.
- `format_reply(value)` — redis-cli-style rendering (see SPEC.md).
- `RedisClient` — `connect()` / `close()` / `command(*args)`; owns
  the socket and a `RespReader`; context-manager support.
- `HELP` — dict: command -> (usage, summary, since, group). Groups
  derived from it for `help @<group>`. Curated subset only (SPEC
  divergence 2).
- `split_command(line)` — `shlex.split`, returning `None` for blank
  lines and raising a friendly error on unbalanced quotes.
- `run_repl(client, input, output)` — prompt loop; injectable streams
  so tests drive it without a tty. Handles `help`/`quit`/`exit`
  client-side, bare-known-command hint (SPEC Step 5), server errors
  printed via `format_reply`, connection loss aborts the loop with
  an error message.
- `main(argv)` — option preprocessing (see below), argparse, then
  one-shot or REPL dispatch. Returns an int exit code; the `__main__`
  block calls `sys.exit(main())`.

## Option parsing quirk

argparse natively accepts `-h`/`--host` and `-p`/`--port`. The page
uses `-h localhost -p 6379`; the sibling memcached-cli project also
accepted `-host`/`-p`. To accept both without fighting argparse,
`main()` rewrites leading option tokens `-host` -> `--host`,
`-port` -> `--port`, `-timeout` -> `--timeout` before parsing.
Positional arguments after the options are the one-shot command; a
`--` separator is honoured by argparse as usual. Note: `-h` is
argparse's built-in help flag, so `--host` must be spelled out when
the user also wants `-h` as host — argparse resolves `-h` to help;
this is standard argparse behaviour and is documented in README.md
(use `--host` to avoid the clash). Wait — this needs care: defining
`--host` with short `-h` would collide with argparse's help. Decision:
do NOT define `-h` as host; define `-p`/`--port`, `--host`,
`--timeout`. The page's `-h localhost` form therefore maps via the
rewrite? No: `-h` alone cannot be both. Resolution: the rewrite maps
`-host` -> `--host` only; `-h` remains argparse help, and README
documents `--host`/`-p` as the supported spellings, with `-h`
printing help. The page's example uses `-h localhost -p 6379`; users
of this build write `--host localhost -p 6379`. This is a documented
divergence, chosen over hand-rolled parsing (minimum code).

Correction to the paragraph above (kept for honesty): the first draft
of this file claimed `-h` host support; it is NOT supported, for the
argparse reason given. SPEC.md's Step 3 section is accurate
(`-h` there refers to the page's example, and README states the
actual spellings).

## What is deliberately NOT built

- RESP3, TLS, AUTH, pub/sub, transactions, cluster/sentinel, binary
  values, inline hints, `--file` batch mode, command completion.
  Each would add surface the page does not require at Steps 1–4.

## Verifiable success criteria

- `python3 -m unittest discover -s tests -v` passes: RESP codec
  round-trips incl. all page examples and invalid inputs; one-shot
  and REPL flows against the fake server; help output; connection
  failure handling; exit codes.
- By hand against the in-repo redis-server (read-only oracle):
  `redis_cli.py --port <port> PING` prints `PONG`;
  `SET`/`GET`/`INCR` round-trip; REPL prompt shows host:port.
