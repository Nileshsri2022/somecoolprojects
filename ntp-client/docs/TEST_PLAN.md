# TEST_PLAN — NTP Client

## How to run

```
cd ntp-client
python3 -m unittest discover -s tests -v
```

Python 3 standard library only; no test dependencies.

## Test strategy

No test contacts a real public NTP server, and no test touches the
system clock. All network tests use a local fake NTP server: a
one-shot UDP thread bound to `127.0.0.1` on an ephemeral port
(port 0, read back from the socket), replying once and then exiting.
Each test joins its server thread, so no server is left running.
Timeout tests bind a UDP socket that never replies, on an ephemeral
port, and close it afterwards.

The fake server (`make_response` in the test file) echoes the request's
transmit field into the origin field — exactly what a real NTP server
does — and fills receive/transmit timestamps from fixed values, so
offset/delay assertions are deterministic where they should be and
loopback-timing assertions are only bounds, not exact values. In this
sandbox those exchange tests are skipped (see Sandbox note below);
they are still present and run wherever loopback UDP works.

## Coverage (by area)

- **Epoch conversion**: Unix 0 maps to NTP offset 2208988800; round
  trips for several values; half-second fraction is exactly 2^31;
  pre-1970 input rejected.
- **Request packet**: exactly 48 bytes; first byte `0x23` (LI 0,
  version 4, mode 3); transmit field equals the given time; all other
  fields zero.
- **Response parsing**: all header/timestamp fields decoded;
  short packets, client-mode replies, stratum-0 replies and origin
  mismatches all rejected; packets longer than 48 bytes accepted.
- **Offset/delay math**: the page's formulas checked on hand-computed
  cases (zero offset with symmetric delay; +5 s offset with 2 s delay;
  symmetric zero-delay case).
- **Full exchange against the fake server**: stratum, host and server
  timestamps as served; delay is non-negative and under the timeout;
  delay equals `(t3 − t0) − (t2 − t1)` from the returned timestamps;
  the bytes the fake server received are a 48-byte `0x23` client packet.
- **Failure paths**: silent server → `NtpError` (and CLI exit code 1);
  stratum-0 server → `NtpError`.
- **CLI**: exit code 0 and "Offset:" / "Round-trip delay:" /
  "NOT changed" in output against the fake server.

## What the tests do NOT prove

- Behaviour against a real public NTP server (pool.ntp.org port 123):
  not attempted from this sandbox, so UDP reachability to the public
  Internet and accuracy against a real server clock are unverified.
  A user-side check is: `python3 ntp_client.py pool.ntp.org` from a
  machine with UDP/123 egress, and compare the printed server time
  with a known-good clock.
- System-clock setting: not implemented (SPEC Step 4), so nothing
  about it is tested.
- IPv6, authentication, and multi-server selection: out of scope
  (see SPEC.md).

## Sandbox note (observed 2026-10-25)

UDP loopback (127.0.0.1) is BLOCKED in this sandbox: `sendto` raises
`PermissionError` (Errno 1, "Operation not permitted"), the same class
of sandbox UDP block seen by earlier waves. The suite therefore skips
the 6 tests that need a live loopback exchange plus the loopback
timeout/CLI tests (7 skips total, including the dedicated
loopback-attempt test, which documents the block by skipping with that
message). Packet encode/decode, parsing validation and formula tests
(16 tests) run and pass without any socket. This is an environment
restriction, not a code defect to paper over: on an unblocked machine
the same suite runs the fake-server exchange tests with no code change.
First run here, before the skip logic: 22 tests, 4 errors + 1 failure,
all from the loopback block except that the failures also exposed a
real test-helper bug (the fake server echoed the wrong request bytes
as the origin field) — fixed, see the comment in `make_response`.
