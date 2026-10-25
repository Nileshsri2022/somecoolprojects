# TEST_PLAN — Traceroute

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

All tests are stdlib `unittest`, no network, no privileges, no
live sockets. The fake transport stands in for `RealTransport`.

## Coverage map (challenge step → test)

- Step 1 header: `format_header` exact string for the page's example
  values; payload is exactly 32 bytes and equals the page's string.
- Step 2 sockets/ports: `port_for` starts at 33434, increases per
  probe, stays in 33434–33534, wraps to 33434 after 33534.
- Step 3 hostname: `resolve_display` returns `host (ip)` on success
  and `ip (ip)` on lookup failure (monkeypatched `gethostbyaddr`).
- Step 4 TTL loop/timeouts: fake-transport traces stop at the
  destination hop, stop at max-hops when never reached, record
  all-`*` hops without stopping, and record mixed timeout/answer hops.
- Step 5 timing/format: `format_hop` renders single-probe hops,
  three-probe same-host hops, all-`*` hops (`3  * * *`), and
  multi-responder hops as a hop line plus continuation lines;
  RTTs print with three decimals (`5.131 ms`).
- ICMP parsing (crafted byte strings, no sockets):
  - Time Exceeded (11/0) with embedded UDP header → type, code,
    embedded destination port recovered.
  - Destination Unreachable / Port Unreachable (3/3) → reached.
  - Echo Reply (0/0) with matching id/sequence → reached.
  - Truncated, empty, and garbage packets → `None`, no exception.
  - `is_destination_reached` truth table for types 0, 3/3, 3/1, 11.
- ICMP Echo building: `checksum` of a known vector; built packet has
  type 8, code 0, the given id/sequence, and a self-consistent
  checksum (re-checksumming the packet yields 0).
- CLI: no-argument invocation exits non-zero with usage on stderr;
  `main()` with an injected fake transport prints header + hop lines
  for a scripted two-hop trace (proves header/format/loop wiring
  without a socket).

## Success criteria

Every test passes; no test opens a socket, binds a port, or needs
root. A live trace is verified only by hand, where privileges allow,
and its result is reported as observed — never inferred from tests.

## What is NOT tested here (and why)

Live end-to-end tracing: it needs raw-socket privileges and a real
network path, neither of which the unit-test environment can assume.
If run by hand as root / with `CAP_NET_RAW`, expected behaviour is:
TTL 1 answers from the local gateway, later hops increment, and the
final hop is marked reached (UDP: port-unreachable; ICMP: echo reply).
