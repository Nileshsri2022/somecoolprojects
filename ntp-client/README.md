# Build Your Own NTP Client

A Network Time Protocol client in Python 3 (standard library only),
built for the Coding Challenges challenge:

- Challenge page: https://codingchallenges.fyi/challenges/challenge-ntp
- Protocol: RFC 5905, section 7 (48-byte UDP packet, port 123)

## Usage

```
python3 ntp_client.py [host] [--port N] [--timeout S] [--json]
```

Default host is `pool.ntp.org`, default port 123, default timeout 5 s.
Example output (against a server):

```
NTP server: pool.ntp.org:123  (stratum 2, version 4, leap 0)
t0 client send:    ...
t1 server receive: ...
t2 server send:    ...
t3 client receive: ...
Offset: ... s  (server - local; add this to local time)
Round-trip delay: ... s
Server time: ...
Corrected local time (not applied): ...
NOTE: the system clock was NOT changed. See docs/SPEC.md Step 4.
```

`--json` prints the same result as JSON, with ISO-8601 companions for
every timestamp.

## What it does (challenge steps 0–3)

1. Sends a 48-byte client request (first byte `0x23`: LI 0, version 4,
   mode 3) with the client's send time as the transmit timestamp.
2. Decodes the response and prints the four timestamps (t0–t3), plus
   stratum, version, leap indicator, root delay/dispersion and
   reference timestamp.
3. Computes offset θ = ((t1 − t0) + (t2 − t3)) / 2 and round-trip
   delay δ = (t3 − t0) − (t2 − t1), exactly as the challenge page
   defines them.

## What it does NOT do (challenge step 4, deliberately)

**It never sets the system clock.** The challenge's Step 4 asks the
builder to change their machine's clock (even to an hour earlier, then
correct it) and loop until the offset is below ±0.5 ms. This build
prints the corrected local time instead and applies nothing; there is
no `--set-clock` option. See `docs/SPEC.md` for the full statement.

Other scope limits: single-server, single exchange per run (no polling
loop, no multi-server / intersection-algorithm selection, no slewing);
no NTP authentication or extension fields; IPv4 only. All are recorded
honestly in `docs/SPEC.md`.

## Verified vs not verified

- Verified (tests, no socket needed): packet encoding/decoding,
  timestamp conversion, offset/delay formulas, and origin/mode/stratum
  validation.
- NOT verified in this sandbox: a full UDP exchange against the local
  fake server, because this sandbox blocks UDP loopback (`sendto` to
  127.0.0.1 → EPERM). The suite probes for this and skips those 7
  tests with that message instead of faking a pass; on an unblocked
  machine the same suite runs them against the fake server (127.0.0.1,
  ephemeral port) with no code change. Also not verified: querying a
  real public NTP server, accuracy against a real server clock, or any
  clock change. No live time sync is claimed. User-side check:
  `python3 ntp_client.py pool.ntp.org` on a machine with UDP/123 egress.

## Tests

```
python3 -m unittest discover -s tests -v
```

See `docs/TEST_PLAN.md` for coverage and limits.

## Files

- `ntp_client.py` — the whole client
- `docs/SPEC.md` — challenge steps, divergences, scope limits
- `docs/DESIGN.md` — packet layout and design decisions
- `docs/TEST_PLAN.md` — test coverage
- `tests/test_ntp_client.py` — unittest suite (fake local server only)
