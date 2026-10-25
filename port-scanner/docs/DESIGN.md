# DESIGN — Port Scanner

## Assumptions (stated before coding, ponytail rule)
1. Python 3 stdlib only: `socket`, `argparse`, `concurrent.futures`,
   `ipaddress`, `sys`. No third-party packages, no raw sockets.
2. Single main file `scanner.py`: library functions + `main()` CLI.
   Importing it must not scan anything (`if __name__ == "__main__"`).
3. TCP connect scan only (see SPEC.md divergence on SYN scan).
4. Output is the page's format, sorted ascending by port, regardless
   of the order threads finish in. Sweep output is grouped per host,
   in the order hosts were expanded.
5. Defaults: timeout 0.5 s, workers 100, ports 1–65535 when neither
   `--port` nor `--ports` is given. These keep a full vanilla scan of
   loopback fast while staying inside the page's timeout suggestion.

## Components
- `scan_port(host, port, timeout) -> str`: one `socket.create_connection`
  with timeout; maps result to `open` / `closed` / `filtered` / `error`.
  The socket is always closed (context manager). A `socket.gaierror`
  (DNS failure) returns `error`, not `filtered`, so a typo'd hostname
  is not silently reported as a firewall.
- `parse_ports(spec) -> list[int]`: parses `80`, `80,443`, `1-1024`,
  `80,8000-8010`; validates 1–65535, rejects reversed ranges and
  empty parts; deduplicates and sorts.
- `expand_hosts(spec) -> list[str]`: comma list, then per item:
  wildcard `*` only as the final octet (e.g. `127.0.0.*`) expands to
  .1–.254; CIDR (contains `/`) expands via `ipaddress.ip_network`
  `.hosts()`; anything else passes through unchanged. Wildcard/CIDR
  expansion is capped: a `/16` or larger expansion would be thousands
  of hosts, so networks with a prefix shorter than /24 are rejected
  with a clear error (a sweep that big is not a sensible CLI default
  and would look like network abuse).
- `scan_host(host, ports, timeout, workers) -> dict[int, str]`:
  `ThreadPoolExecutor(max_workers=workers)` over `scan_port`; results
  collected into a dict keyed by port.
- `main(argv) -> int`: argparse CLI, prints `Scanning host: ...`
  header(s), `Port: N is open` lines (plus closed/filtered lines
  only with `--show-all`), and a one-line summary per host
  (`N open / M scanned`). Returns 0 on success, 2 on bad arguments
  (argparse default) or an unresolvable host.

## Why threads, not processes or asyncio
Thread-per-port with a thread pool is the simplest stdlib way to get
concurrency for I/O-bound connect attempts; the GIL is not a
bottleneck because threads spend their time blocked on connect.
`socket.create_connection` per port keeps each attempt independent
and timeout-bounded.

## Error handling
- Invalid port/range/host spec: argparse error, exit 2, message on
  stderr. No partial scan output in that case.
- DNS failure for a host: that host's scan reports `error` and the
  CLI exits non-zero after printing the other hosts' results, rather
  than crashing mid-sweep.
- Keyboard interrupt: executor shuts down; partial results are not
  printed as if complete.

## Verifiable success criteria
- Open loopback test server is reported `open`; a closed loopback
  port is reported `closed`; a forced timeout is reported `filtered`
  (unit test via monkeypatched socket).
- Range parsing, host expansion (list / wildcard / CIDR), and CLI
  output format are all covered by tests; full suite green before
  delivery.
