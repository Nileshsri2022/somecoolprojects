# Socat — Specification

## Challenge source (resolved, not guessed)

- Challenge page: https://codingchallenges.fyi/challenges/challenge-socat
  ("Build Your Own Socat", Coding Challenge #79, John Crickett).
  Found via the site's tag index: https://codingchallenges.fyi/challenges/tags/networking/
  (the "Build Your Own Socat" entry there links to the page above),
  cross-checked against the newsletter mirror
  https://codingchallenges.substack.com/p/coding-challenge-79-socat
  (same steps, same example commands).
- The page was read in full before any code was written.

## What socat is (per the page)

`socat` establishes two bidirectional byte streams and transfers data
between them. The streams can be built from files, pipes, devices,
sockets (UNIX, IP4, IP6, raw, UDP, TCP), SSL sockets and proxy CONNECT
connections — basically anything a Unix-like OS treats as a file.

## Challenge steps and implementation status

| Step | Page requirement | Status |
|------|------------------|--------|
| Step 0 | Set up the environment | Done (Python 3 stdlib only). |
| Step 1 | `socat - TCP4:eu.httpbin.org:80` — bidirectional relay between stdio and a TCP4 connection; hand-crafted HTTP request must get a response. | Done. `TCP`/`TCP4`/`TCP6` connect supported. Verified locally against a local TCP echo server (no internet dependency in tests); the httpbin example is a manual check, not a test. |
| Step 2 | `socat -u STDIO FILE:test.txt,create` — unidirectional stdio → file, creating the file; EOF (Ctrl-D) terminates. | Done. `-u` implemented; `FILE` with `create` (and the page's Step-3 spelling `creat`, accepted as an alias). |
| Step 3 | `socat -u TCP4-LISTEN:3333,reuseaddr,fork OPEN:./test.log,creat,append` — TCP listen with `reuseaddr` and `fork` (one handler per connection), writing each connection's bytes to a log file opened with `creat,append`, as a simple network message collector. | Done. `TCP-LISTEN`/`TCP4-LISTEN` with `reuseaddr` and `fork`; `OPEN` is an alias of `FILE`; `append` supported. Each forked connection opens the file afresh, so concurrent writers append rather than share one offset. |
| Step 4 | `socat -u EXEC:'tail -f test.txt' TCP4:localhost:3333` — `EXEC` address so a tailed log file can be sent to the Step-3 collector. | Done. `EXEC:'command'` runs the command (shlex-split; see DESIGN.md) and relays its stdout (and, bidirectionally, its stdin). |
| Going Further | "Have a read of the manual… If you've never used UDP before that might be an interesting place to start." | Done, as an extension: `UDP`/`UDP4`/`UDP6` connect and `UDP-LISTEN` are implemented and tested. |

## Command-line interface

```
socat [-u | -U] [-v] address1 address2
socat -h | --help
```

- `-u`: unidirectional, left address → right address only.
- `-U`: unidirectional, right address → left address only.
- Default (neither flag): bidirectional relay.
- `-v`: log connection/relay events to stderr.
- Exactly two addresses are required; anything else is a usage error (exit 1).

## Address types supported

| Address | Meaning | Options |
|---------|---------|---------|
| `-`, `STDIO`, `STDIN`, `STDOUT` | Standard input/output (fd 0 / fd 1). `STDIN` is read-only, `STDOUT` write-only. | — |
| `FILE:path`, `OPEN:path` | Regular file (same behaviour for both spellings). | `create`/`creat`, `append`, `trunc`, `excl` (fail if the file already exists, only with `create`) |
| `TCP:host:port`, `TCP4:host:port`, `TCP6:host:port` | TCP client connection. Host may be a name or IP; port is decimal. | `bind=addr` (local bind address) |
| `TCP-LISTEN:port`, `TCP4-LISTEN:port`, `TCP6-LISTEN:port` (also `TCP-LISTEN:host:port`) | TCP server: bind, listen, accept. | `reuseaddr`, `fork` (one thread per connection, each opening a fresh right-hand address), `bind=addr`, `backlog=n` |
| `UDP:host:port`, `UDP4:host:port`, `UDP6:host:port` | Connected UDP socket. | `bind=addr` |
| `UDP-LISTEN:port`, `UDP4-LISTEN:port`, `UDP6-LISTEN:port` | UDP server: bind; the first datagram fixes the peer, replies go to that peer. | `reuseaddr`, `bind=addr` |
| `EXEC:'command'` | Run a command; its stdout is the read side, its stdin the write side. | — (the command itself is the argument) |

Options are comma-separated after the address, e.g.
`TCP4-LISTEN:3333,reuseaddr,fork`. Unknown options are rejected with an
error instead of being silently ignored. The page's Step-3 spelling
`creat` is accepted as an alias for `create`.

## Behaviour

- Relay is byte-for-byte, binary-safe (no newline translation, no encoding).
- Bidirectional mode uses one copy thread per direction. EOF on one side
  half-closes the other side where the destination supports it (TCP
  `shutdown(SHUT_WR)`); the relay exits once both directions have ended.
- Unidirectional mode (`-u`/`-U`) copies one direction only and exits on
  source EOF.
- A `TCP-LISTEN` without `fork` serves exactly one connection and then exits.
  With `fork`, it serves connections until killed (Ctrl-C / SIGTERM).
- A file opened without `create`/`creat` must already exist, otherwise the
  program exits with an error. `append` opens at end-of-file; `trunc`
  empties an existing file. `append` and `trunc` together are an error.
- Exit codes: `0` normal completion, `1` usage/address/connection error,
  `130` on Ctrl-C (SIGINT).

## Deliberate divergences from real socat

- This is a documented subset, NOT full socat compatibility. Real socat
  has dozens of address types and hundreds of options; only the table
  above is implemented.
- `fork` is implemented with threads, not OS `fork()`. Observable
  behaviour (one independent handler per connection, fresh right-hand
  address per connection) is the same for the Step-3 use case.
- `EXEC` commands are split with `shlex` and executed without a shell,
  so shell metacharacters (pipes, redirects, globbing) inside the quoted
  command are NOT interpreted. `tail -f file` and `echo hello` work;
  `echo a | cat` does not. This is a safety choice, documented here and
  in `--help`.

## NOT built (stated plainly)

- SSL/TLS sockets (`OPENSSL`, `OPENSSL-LISTEN`, etc.) — not built.
- Proxy CONNECT, SOCKS — not built.
- UNIX-domain sockets (`UNIX-LISTEN`, `UNIX-CONNECT`) — not built.
- Raw IP sockets, serial devices, pseudo-terminals (`PTY`), tun/tap —
  not built; raw sockets need privileges and are out of scope for an
  unprivileged tool.
- The rest of real socat's address/option catalogue (address ranges,
  `retry`, `forever`, `crnl`, datagram `UDP-RECVFROM`, multicast, etc.)
  — not built.
- No daemon mode, no PID files, no logging to syslog.
- IPv6 is attempted via `TCP6`/`UDP6` but is only exercised on loopback
  where available; the test suite does not require IPv6.
