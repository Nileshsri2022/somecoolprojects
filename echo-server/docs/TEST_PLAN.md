# Echo Server — TEST_PLAN

Suite: `tests/test_echo_server.py`, run with:

```
python3 -m unittest discover -s tests -v
```

All tests use ephemeral ports (port `0` — the OS picks a free port) on
`127.0.0.1`, so they never need privileges and never collide with a
real echo service. No test uses `pkill`; subprocess tests hold the
child's `Popen` object and signal/terminate that explicit PID only.

## Cases

### TCP (all expected to pass in this sandbox)

1. `test_tcp_single_message_echo` — one client, one message, exact echo.
2. `test_tcp_multiple_messages_same_connection` — several messages on
   one connection, each echoed in order, including an empty-ish binary
   payload (raw bytes, not just text).
3. `test_tcp_binary_and_large_payload` — binary bytes (all byte values)
   and a 1 MiB payload echoed byte-for-byte (proves chunked echoing
   neither truncates nor corrupts).
4. `test_tcp_concurrent_clients` — 5 clients in parallel threads, each
   sending a distinct message, each receiving exactly its own message
   (proves per-client threads, no cross-talk).
5. `test_tcp_server_stays_up_after_disconnect` — a client connects and
   disconnects; a second client then still gets an echo (proves the
   server does not exit after one connection, Step 3 vs Step 2).
6. `test_tcp_accept_log_message` — server stdout contains
   `Accepted connection from: 127.0.0.1:` after a connection (proves the
   challenge's log format; uses a subprocess server so stdout is real).
7. `test_tcp_clean_shutdown_via_sigint` — subprocess server, SIGINT
   sent to its explicit PID, process exits with code 0 within 5 s and
   prints `Server shutting down` (proves clean shutdown, Step 6).
8. `test_cli_udp_flag_parses` — `--udp`/`-udp` select UDP mode and the
   default mode is TCP (argparse-level; does not need a socket).

### UDP

9. `test_udp_datagram_echo` — one UDP datagram echoed back unchanged to
   its sender, and a second datagram from a second socket echoed back
   to that socket.
   - **Expected result in this sandbox: SKIPPED, not passed.** UDP
     loopback is blocked here: the UDP server binds fine, but a UDP
     `sendto` fails with `PermissionError: [Errno 1] Operation not
     permitted` (verified by a direct probe before this suite was
     written, while TCP loopback succeeds). The test attempts a real
     UDP round-trip and calls `skipTest` with that reason when the OS
     refuses the send. It must not be reported as a UDP pass. On a
     normal machine it should run and pass; re-run it there before
     claiming UDP verified end-to-end.

## Manual checks (not automated)

- `python3 echo_server.py --port 7007`, then in another terminal
  `nc localhost 7007`, type a line, confirm it echoes, Ctrl+C the
  server, confirm it exits cleanly. (Needs `nc` installed; not part of
  the automated suite.)
- `python3 echo_server.py --port 7007 --udp`, then
  `nc -u localhost 7007` — same check over UDP (needs a machine where
  UDP loopback is not blocked).

## What is not tested

- Binding port 7 itself (needs privileges; behaviour is port-independent
  and the code path is identical — only the port number differs).
- Binding all interfaces (`--host ""`) in tests: tests bind loopback so
  they are hermetic; the default-host code path is the same `bind`
  call with a different host string.
