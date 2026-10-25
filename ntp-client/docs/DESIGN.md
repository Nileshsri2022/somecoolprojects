# DESIGN — NTP Client

## Layout

```
ntp-client/
  ntp_client.py        # the whole client (stdlib only)
  README.md
  docs/SPEC.md         # challenge steps, divergences, scope limits
  docs/DESIGN.md       # this file
  docs/TEST_PLAN.md    # test coverage and how to run it
  tests/test_ntp_client.py
```

One main file is deliberate: the protocol is a single 48-byte packet
plus four timestamps, so splitting it across modules would add
indirection without benefit.

## Packet format (RFC 5905 §7, as cited by the challenge page)

48 bytes, big-endian:

| Bytes | Field |
|------:|-------|
| 0 | LI (2 bits) \| version (3 bits) \| mode (3 bits) |
| 1 | Stratum |
| 2 | Poll |
| 3 | Precision (signed) |
| 4–7 | Root delay (signed 16.16 fixed point) |
| 8–11 | Root dispersion (unsigned 16.16 fixed point) |
| 12–15 | Reference identifier |
| 16–23 | Reference timestamp |
| 24–31 | Origin timestamp (t0, echoed from request) |
| 32–39 | Receive timestamp (t1) |
| 40–47 | Transmit timestamp (t2) |

Each timestamp is 32-bit seconds since 1900-01-01 plus a 32-bit
fraction of a second. Conversion uses the constant
`NTP_EPOCH_OFFSET = 2208988800` (seconds between 1900 and 1970).

## Request construction (`build_request`)

- First byte `0x23`: LI 0 (no warning), version 4, mode 3 (client).
- Stratum, poll, precision, root delay/dispersion, reference id,
  reference, origin and receive timestamps are all zero — a client
  has nothing meaningful to put there yet.
- Transmit timestamp = the client's send time. `query()` captures
  `t0 = time.time()` first and passes it in, so the timestamp in the
  packet and the t0 used in the offset/delay math are the same instant,
  not two nearby instants.

## Response parsing (`parse_response`)

- Reject packets shorter than 48 bytes (longer ones are accepted; any
  extension/authenticator tail is ignored, per SPEC divergence 4).
- Reject mode != 4 (server). Reject stratum 0 (unsynchronised /
  kiss-of-death) with the reference id in the error message.
- If an expected origin is supplied, reject a mismatch — the reply is
  not an answer to this request.
- Root delay/dispersion are decoded from their 16.16 fixed-point form
  (divided by 65536) for display; they are not used in offset/delay.

## Offset and delay (`compute_offset_delay`)

Exactly the challenge page's formulas, on Unix timestamps in seconds:

- θ = ((t1 − t0) + (t2 − t3)) / 2
- δ = (t3 − t0) − (t2 − t1)

A positive θ means the server clock is ahead of the local clock; the
corrected local time is `t3 + θ`. It is printed only — never applied.

## Exchange (`query`)

One UDP datagram out, one datagram back, with a socket timeout
(default 5 s, `--timeout`). Timeouts and socket errors are converted to
`NtpError` and reported by the CLI as `error: ...` with exit code 1,
instead of a traceback. The socket is always closed (`finally`).

## CLI (`main`)

```
python3 ntp_client.py [host] [--port N] [--timeout S] [--json]
```

Default host `pool.ntp.org`, default port 123. Output is human-readable
by default (timestamps, offset, delay, server time, corrected time with
a "NOT changed" note) or JSON with `--json` (ISO-8601 companions for
every timestamp field). There is intentionally no clock-setting flag.

## Error handling summary

| Condition | Behaviour |
|-----------|-----------|
| Short packet (< 48 bytes) | `NtpError` |
| Non-server mode | `NtpError` |
| Stratum 0 | `NtpError` (ref-id shown) |
| Origin mismatch | `NtpError` |
| Timeout / UDP error | `NtpError`, CLI exit 1 |
| Pre-1970 transmit time | `ValueError` from `unix_to_ntp` |

## Decisions and trade-offs

- **IPv4 only** (`AF_INET`): keeps the socket code to one path; the
  page's steps do not require IPv6, and the limit is recorded in SPEC.
- **Single exchange, no retry loop in the client**: retries belong to
  a polling daemon, which is out of scope (SPEC divergence 3). The
  caller can re-run the command.
- **No third-party NTP library**: the point of the challenge is the
  packet format, and `struct` + `socket` cover it completely.
