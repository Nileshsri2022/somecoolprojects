# SPEC — Build Your Own NTP Client

## Source challenge (resolved, not guessed)

- Challenge page: https://codingchallenges.fyi/challenges/challenge-ntp
  ("Build Your Own NTP Client")
- How it was found: the codingchallenges.fyi tag index
  (https://codingchallenges.fyi/challenges/tags) → the "intermediate" tag
  page (https://codingchallenges.fyi/challenges/tags/intermediate/) →
  the "Build Your Own NTP Client" link on that page. The page was read in
  full before any code was written.
- Tags on the site: intermediate, networking.
- Protocol reference cited by the page: RFC 5905
  (https://datatracker.ietf.org/doc/html/rfc5905), section 7 (packet
  format). The page also points at a gist list of time servers and the
  NTP Pool Project (https://www.ntppool.org) for real servers.

## Challenge steps, and what this build does for each

### Step 0 — Environment setup
Done. Python 3 standard library only, no dependencies to install.
Run: `python3 ntp_client.py [host] [--port N] [--timeout S] [--json]`.

### Step 1 — Send a request, receive a response (port 123)
Done. The client builds a 48-byte UDP packet, first byte `0x23`
(LI 0, version 4, mode 3 = client), all other fields zero except the
transmit timestamp (the client's send time, t0), sends it to the server
on UDP port 123 by default, and reads the reply. On receipt it checks
the first three fields in the sense the page asks: the response must be
server mode (4), and a stratum-0 reply is rejected as unsynchronised /
kiss-of-death. It additionally checks that the origin timestamp echoes
this request's transmit timestamp, so a stray or mismatched reply is
not silently accepted — this is stricter than the page, and is listed
as a divergence below.

### Step 2 — Decode the response, print the four timestamps
Done. The client prints t0 (client send), t1 (server receive),
t2 (server send) and t3 (client receive), plus stratum, version, leap
indicator, root delay/dispersion, reference id and reference timestamp.
`--json` prints the same data as JSON.

### Step 3 — Offset and round-trip delay
Done, using the page's formulas exactly:
- Offset θ = ((t1 − t0) + (t2 − t3)) / 2
- Round-trip delay δ = (t3 − t0) − (t2 − t1)

t0 is the transmit timestamp written into the request itself, and t3 is
captured immediately after `recvfrom` returns, so both use the same
instants the packet carries / the exchange observes.

### Step 4 — Set the system clock
NOT BUILT, deliberately. The page asks the builder to set their system
clock (even to an hour earlier first, then correct it) and to loop
until the offset is below ±0.5 ms. This build refuses that step:
changing the machine clock is a privileged, system-wide side effect
that this task explicitly forbids, and no `--set-clock` option exists.
Instead the client prints the corrected local time ("not applied") so
the offset can be inspected without touching the clock. This is the
one step that is knowingly incomplete, and it is stated here, in
DESIGN.md, TEST_PLAN.md and the README, not hidden.

## Deliberate divergences from the page

1. **No clock setting (Step 4).** See above. Print-only by design.
2. **Origin-timestamp validation.** The page only asks to "check that
   the first three fields are correct". This client also rejects a
   response whose origin field does not echo the request's transmit
   timestamp. This is standard NTP client hygiene and can only reject
   replies that are not answers to this request.
3. **Single-server query, no polling loop / server selection.** The
   page describes clients that "regularly poll one or more NTP servers"
   and mentions the intersection algorithm, but its steps only require
   one request/response exchange and one offset/delay computation.
   This build does exactly one exchange per run. No Marzullo /
   intersection algorithm, no multi-server selection, no slewing loop.
4. **No authentication / extension fields.** Only the base 48-byte
   header is built and parsed. Packets longer than 48 bytes are
   accepted (the extra bytes are ignored); packets shorter than 48
   bytes are rejected. Symmetric-key / Autokey authentication is not
   implemented and is not required by the page's steps.
5. **Default server is `pool.ntp.org`.** The page offers a gist list or
   the NTP Pool Project; `pool.ntp.org` is the Pool's standard entry
   point, so it is the default host, overridable as a positional
   argument.

## NOT built / scope limits

- Setting or slewing the system clock (Step 4) — see above.
- Multi-server polling, intersection/Marzullo server selection,
  drift estimation over time, or a daemon mode.
- NTP authentication, Kiss-o'-Death rate-limit handling beyond
  rejecting stratum 0 (a KoD packet's ref-id is shown in the error).
- IPv6: the socket is `AF_INET` (IPv4) only. A hostname resolving to
  IPv6 only will fail with a UDP error rather than falling back.
- No live verification against a real public NTP server was performed
  in this sandbox (see TEST_PLAN.md): all exchange tests use a local
  fake server. A real-server run is a user-side check, not a claim made
  here.

## What was verified vs what was not

- Verified: packet encoding/decoding, all four timestamps, offset and
  delay formulas, and origin/mode/stratum validation — all without
  any socket, in the unittest suite.
- NOT verified (sandbox block, honestly recorded): a full UDP exchange
  against the local fake NTP server could NOT run here, because this
  sandbox blocks UDP loopback — `sendto` to 127.0.0.1 raises
  `PermissionError` (Errno 1, "Operation not permitted"). The suite
  probes for this, skips the 6 exchange/CLI tests that need loopback,
  and keeps a dedicated loopback-attempt test documenting the outcome,
  instead of passing or failing spuriously. On a machine without that
  block the same suite runs the exchange tests against the fake server
  (127.0.0.1, ephemeral port) with no code change.
- NOT verified: talking to a real public NTP server (e.g. pool.ntp.org
  port 123) from this sandbox, accuracy against a real server's clock,
  or any system-clock change. No live time sync is claimed.
