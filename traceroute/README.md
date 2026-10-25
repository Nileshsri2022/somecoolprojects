# traceroute — Build Your Own Traceroute

Coding Challenges #24, worked in `somecoolprojects/`.
Docs first, then code — see `docs/` (`SPEC.md`, `DESIGN.md`,
`TEST_PLAN.md`).

Sends TTL-incrementing probes (UDP by default, ICMP Echo with
`--method icmp`) and reports each hop from the ICMP replies:
Time Exceeded from intermediate routers, Destination Unreachable /
Port Unreachable or Echo Reply from the destination, `*` for a
probe that times out.

## Usage

```sh
python3 traceroute.py [-m MAX_HOPS] [-q PROBES] [-w TIMEOUT]
                      [--method udp|icmp] [--no-resolve] HOST
python3 traceroute.py dns.google.com
python3 traceroute.py -m 64 -q 1 dns.google.com   # page's Step 4/5 shape
```

Output shape (page's Step 1 + Step 5 forms):

```
traceroute to dns.google.com (8.8.4.4), 30 hops max, 32 byte packets
 1  192.168.68.1 (192.168.68.1) 5.131 ms
 2  broadband (192.168.1.1) 4.999 ms
 3  * * *
```

A hop whose probes are answered by different routers prints the
extra responders on continuation lines, as in the page's intro
example. A hop of all `*` never stops the trace.

## Privileges — read this before running a live trace

Receiving ICMP replies needs a raw socket (root / `CAP_NET_RAW`
on Linux), and the sandbox may additionally block outbound probes.
In this sandbox a live run prints the header correctly and then
fails cleanly:

```
traceroute to dns.google.com (198.18.37.76), 2 hops max, 32 byte packets
traceroute: probe failed ([Errno 1] Operation not permitted). ...
```

No live trace is claimed from that run. On a machine with the
privileges and a permitted path, the same command traces for real;
all packet building, parsing, and formatting is covered by the
unit tests regardless.

## Divergences from the challenge page

- Max hops default 30 (system traceroute's default), not the page's
  64. `-m 64` reproduces the page.
- Probes per hop default 3 (classic traceroute, as in the page's
  intro example), not the single probe of its Step 4/5 examples.
  `-q 1` reproduces those.
- Header packet size is the actual payload length (32, the page's
  Step 1 string); the page's intro example says 52 for a different
  payload.
- `--method icmp` is an addition (the page is UDP-only), added so
  ICMP Echo Reply parsing is exercised end to end.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests are stdlib `unittest`, need no sockets, no privileges, and
no network: packet parsing is tested on hand-built byte strings
and the TTL loop on a scripted fake transport. 26 tests, all
passing at delivery.
