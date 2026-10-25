# SPEC — Memcached CLI Tool (Coding Challenges #18)

## Source note — reconciled 2026-10-25

The task pointed at `https://codingchallenges.fyi/challenges/challenge-memcached-cli/`,
which 404s. The live page is `challenge-memcached-client`
(`codingchallenges.fyi/challenges/challenge-memcached-client/`), read
directly during reconciliation. Its steps, and this tool's coverage:

- Step 1: serialise/deserialise the text protocol (storage commands
  `<cmd> <key> <flags> <exptime> <bytes>\r\n<data>\r\n` with
  `STORED`/`NOT_STORED` replies; retrieval `get <key>*` with
  `VALUE <key> <flags> <bytes>` blocks then `END`). Covered.
- Step 2: CLI args `ccmc -host <host> -p <port> <command>`,
  defaults `localhost` and `11211`, help (`-h`/`--help` via
  argparse). Covered — `-host`/`-p` and `--host`/`--port`
  are both accepted.
- Step 3: connect, send set/get, display the result
  (`ccmc set test 1234`, `ccmc get test` → `1234`). Covered.
- Step 4: `add` and `replace`. Covered. Note a page wording
  error: Step 4 says replace stores only if the server does
  *not* already hold the key — that is add's condition, not
  replace's. This tool follows the protocol (add = only if
  absent, replace = only if present) and `NOT_STORED`
  otherwise.
- Step 5: `append` and `prepend`. Covered.
- Going Further: `cas`, `delete`, increment/decrement.
  Covered except cas *store*: `gets` reports the cas token,
  but storing by cas is out of scope (see Non-goals).

This is the **client** tool, distinct from the Memcached Server project
(`somecoolprojects/memcached-server/`): this tool talks the text protocol to
an already-running server; it does not store anything itself.

## What the tool does

`memcached_cli.py` is a command-line client for a Memcached server speaking
the plain-text protocol over TCP. It supports one-shot commands and an
interactive REPL.

```
python3 memcached_cli.py --host 127.0.0.1 --port 11211 set mykey myvalue
python3 memcached_cli.py --host 127.0.0.1 --port 11211 get mykey
python3 memcached_cli.py --host 127.0.0.1 --port 11211   # REPL
```

## Commands (one-shot subcommands and REPL verbs)

| Command | Form | Server reply handled |
|---|---|---|
| set | `set KEY VALUE [--flags N] [--exptime N]` | `STORED`, `NOT_STORED` |
| add | `add KEY VALUE [--flags N] [--exptime N]` | `STORED`, `NOT_STORED` |
| replace | `replace KEY VALUE [--flags N] [--exptime N]` | `STORED`, `NOT_STORED` |
| append | `append KEY VALUE` | `STORED`, `NOT_STORED` |
| prepend | `prepend KEY VALUE` | `STORED`, `NOT_STORED` |
| get | `get KEY [KEY ...]` | `VALUE ...` blocks, then `END`; missing key prints nothing for that key |
| gets | `gets KEY [KEY ...]` | `VALUE ... <cas>` blocks, then `END` |
| delete | `delete KEY` | `DELETED`, `NOT_FOUND` |
| incr | `incr KEY [AMOUNT]` (default 1) | new value, or `NOT_FOUND` |
| decr | `decr KEY [AMOUNT]` (default 1) | new value, or `NOT_FOUND` |
| touch | `touch KEY SECONDS` | `TOUCHED`, `NOT_FOUND` |
| flush_all | `flush_all` | `OK` |
| stats | `stats` | `STAT k v` lines, then `END` |
| version | `version` | `VERSION x.y.z` |
| quit / exit | REPL only | closes the connection |

Global options (one-shot and REPL): `-host`/`--host` (default
`localhost`), `-p`/`--port` (default `11211`), `--timeout`
seconds (default `5`).

## Protocol details implemented

- Storage commands send: `<cmd> <key> <flags> <exptime> <bytes>\r\n<value>\r\n`
  where `<bytes>` is the byte length of the value (UTF-8 encoded).
- Retrieval reads `VALUE <key> <flags> <bytes> [<cas>]` headers, then exactly
  `<bytes>` bytes plus the trailing `\r\n`, repeated until `END`.
- `incr`/`decr` send `<cmd> <key> <amount>\r\n` and print the numeric reply.
- `stats` prints each `STAT` line verbatim, stopping at `END`.
- `version` prints the server's `VERSION` line verbatim.
- Any `ERROR`, `CLIENT_ERROR ...`, or `SERVER_ERROR ...` line is printed to
  stderr and the command exits non-zero (one-shot) / reports the error (REPL).
- A connection failure prints a clear error to stderr and exits non-zero
  (one-shot) instead of a traceback.
- REPL: blank lines are ignored; `help` lists commands; `quit`/`exit`/EOF
  close the connection cleanly.

## Output contract (one-shot)

- `get`/`gets`: one line per found key: `KEY: VALUE` (gets: `KEY: VALUE (cas=N)`).
  A missing key produces no line and exit code 0 — absence is data, not an error.
- `set`/`add`/`replace`/`append`/`prepend`/`delete`/`touch`/`flush_all`:
  the server's single-word reply (`STORED`, `DELETED`, `OK`, ...) on stdout.
- `incr`/`decr`: the new integer value on stdout.
- `stats`: the `STAT` lines on stdout.
- `version`: the `VERSION` line on stdout.
- Errors go to stderr; exit code 1 on server error, 2 on connection/usage error
  (argparse usage errors keep argparse's exit code 2).

## Non-goals

- No binary protocol, no UDP, no SASL/auth, no TLS.
- No `cas` store command (gets reports the cas token; storing by cas is out
  of scope for the minimum client).
- No multi-line / binary values via the one-shot CLI: values are single
  command-line arguments (UTF-8). The REPL likewise takes the rest of the
  line as the value, so values may contain spaces but not newlines.
- No configuration file, no daemon mode, no dependency on the
  memcached-server project in this repo.
