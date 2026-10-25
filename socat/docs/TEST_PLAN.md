# Socat — Test Plan

Suite: `tests/test_socat.py`, run with

```
python3 -m unittest discover -s tests -v
```

All tests use ephemeral ports only: a helper binds port 0, reads the
assigned port, closes the socket, and hands the port to the test. Test
listeners are local echo/capture servers on `127.0.0.1` run in daemon
threads with explicit sockets that are closed in `tearDown`, and socat
processes are `subprocess.Popen` objects terminated explicitly by
`proc.terminate()` / `proc.wait()` — never `pkill` patterns. No test
touches the network beyond loopback, so the suite is hermetic (the
page's `eu.httpbin.org` example is a manual check only).

## Cases

CLI / parsing:
- `--help` / `-h` exits 0 and names STDIO, TCP, FILE, EXEC.
- One address (missing second) exits non-zero.
- Unknown address type exits non-zero.
- Unknown option (e.g. `FILE:x,badopt`) exits non-zero.
- `append` + `trunc` together exits non-zero.
- Missing file without `create` exits non-zero.

Step 2 — file (unidirectional):
- `-u STDIO FILE:out,create`: piped stdin lands byte-for-byte in a new file.
- `-u STDIO FILE:out,append`: existing content is preserved, new bytes appended.
- `-u STDIO FILE:out,trunc`: existing content is replaced.
- `-u FILE:in STDIO`: file content is printed to stdout, process exits on file EOF.
- `-u STDIN FILE:out,create` and `-u STDIO OPEN:out,create` aliases work
  (`OPEN` alias, `STDIN` alias).
- `-u STDIO FILE:out,creat`: the page's Step-3 spelling `creat` works.

Step 1 — TCP connect (bidirectional):
- `socat - TCP4:127.0.0.1:port` against a local echo server: stdin bytes
  come back on stdout, process exits after stdin closes and the echo
  server closes on EOF.
- Same via the `TCP:` spelling.
- `-U TCP:host:port STDIO` (reverse unidirectional): a server greeting is
  printed to stdout.

Step 3 — TCP listen / log collector:
- `-u TCP4-LISTEN:port,reuseaddr,fork OPEN:log,creat,append`: three
  sequential clients each send one line; all three lines are in the log
  file afterwards; the collector is stopped explicitly by PID.
- `reuseaddr`: after stopping a listener, a new listener on the same
  port binds immediately.
- Non-fork `TCP-LISTEN`: serves one connection, then the process exits 0.

Step 4 — EXEC:
- `-u EXEC:'echo hello-exec' FILE:out,create`: command output lands in the file.
- `-u EXEC:'printf …' TCP:host:port`: command output arrives at a local
  capture server.

Going Further — UDP:
- `-u STDIO UDP:127.0.0.1:port`: stdin bytes arrive as a datagram at a
  local UDP capture server.
- `-u UDP-LISTEN:port FILE:out,create`: a sent datagram lands in the file;
  terminated explicitly by PID, since a UDP listener cannot know the
  sender is done.
- NOT asserted in this VM: a UDP echo round-trip. The sandbox blocks
  the reply direction (a loopback UDP sendto back to a client port
  raises `PermissionError` or is swallowed, while the initial send to a
  bound port works). On a normal machine, verify manually with
  `socat - UDP:127.0.0.1:port` against a UDP echo server.

## Manual checks (not in the suite)

- `socat - TCP4:eu.httpbin.org:80` + hand-crafted `GET /get` request,
  per Step 1 of the page (needs internet; not asserted by tests).
- `socat -u EXEC:'tail -f test.txt' TCP4:localhost:3333` against the
  Step-3 collector, per Step 4 (needs two terminals; the suite covers
  the same code path with `echo`/`printf` instead of `tail -f`).
