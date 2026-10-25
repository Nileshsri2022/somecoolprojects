#!/usr/bin/env python3
"""Build Your Own NTP Client (codingchallenges.fyi, challenge-ntp).

Python 3 standard library only. Sends one NTP request over UDP (port 123
by default), decodes the 48-byte response, prints the four timestamps and
computes the clock offset and round-trip delay exactly as the challenge
page defines them.

This tool NEVER sets the system clock. See Step 4 in docs/SPEC.md for why
that step is intentionally not implemented.
"""

import argparse
import datetime
import json
import socket
import struct
import sys
import time

NTP_PORT = 123
PACKET_SIZE = 48
NTP_EPOCH_OFFSET = 2208988800  # seconds between 1900-01-01 and 1970-01-01
NTP_VERSION = 4
MODE_CLIENT = 3
MODE_SERVER = 4

# Header layout (RFC 5905, section 7, as cited by the challenge page):
#   byte 0:  LI (2 bits) | version (3 bits) | mode (3 bits)
#   byte 1:  stratum, byte 2: poll, byte 3: precision
#   bytes 4-7:   root delay (signed fixed point, 16.16)
#   bytes 8-11:  root dispersion (unsigned fixed point, 16.16)
#   bytes 12-15: reference identifier
#   bytes 16-23: reference timestamp
#   bytes 24-31: origin timestamp      (t0, echoed from the request)
#   bytes 32-39: receive timestamp     (t1)
#   bytes 40-47: transmit timestamp    (t2)
# Each timestamp is 32-bit seconds since 1900-01-01 + 32-bit fraction.


class NtpError(Exception):
    """Raised for malformed responses, refused servers, or network failures."""


def unix_to_ntp(unix_seconds):
    """Convert a Unix timestamp (float seconds) to an NTP (sec, frac) pair."""
    if unix_seconds < 0:
        raise ValueError("Unix timestamps before 1970 cannot be NTP timestamps")
    ntp = unix_seconds + NTP_EPOCH_OFFSET
    seconds = int(ntp)
    fraction = int(round((ntp - seconds) * (1 << 32))) & 0xFFFFFFFF
    if fraction == (1 << 32):
        fraction = 0
        seconds += 1
    return seconds, fraction


def ntp_to_unix(seconds, fraction):
    """Convert an NTP (sec, frac) pair to a Unix timestamp (float seconds)."""
    return seconds + fraction / float(1 << 32) - NTP_EPOCH_OFFSET


def _pack_timestamp(seconds, fraction):
    return struct.pack(">II", seconds & 0xFFFFFFFF, fraction & 0xFFFFFFFF)


def _unpack_timestamp(data, offset):
    seconds, fraction = struct.unpack_from(">II", data, offset)
    return seconds, fraction


def build_request(transmit_unix=None, version=NTP_VERSION):
    """Build a 48-byte client request. Returns (packet, transmit_ntp_pair).

    First byte 0x23 = LI 0, version 4, mode 3 (client). All fields are zero
    except the transmit timestamp, which is the client's send time (t0).
    """
    if transmit_unix is None:
        transmit_unix = time.time()
    transmit = unix_to_ntp(transmit_unix)
    packet = bytearray(PACKET_SIZE)
    packet[0] = (0 << 6) | (version << 3) | MODE_CLIENT
    packet[40:48] = _pack_timestamp(*transmit)
    return bytes(packet), transmit


def parse_response(data, expected_origin=None):
    """Decode a 48-byte (or longer) NTP response into a dict.

    Raises NtpError on a short packet, a non-server mode, or a stratum-0
    (kiss-of-death / unsynchronised) response. If expected_origin is given,
    a mismatched origin timestamp is also an error: the response does not
    belong to our request.
    """
    if len(data) < PACKET_SIZE:
        raise NtpError("short NTP packet: got %d bytes, need %d"
                       % (len(data), PACKET_SIZE))
    first = data[0]
    leap = (first >> 6) & 0x3
    version = (first >> 3) & 0x7
    mode = first & 0x7
    if mode != MODE_SERVER:
        raise NtpError("unexpected NTP mode %d (expected server mode 4)" % mode)
    stratum = data[1]
    if stratum == 0:
        raise NtpError("stratum 0: server is unsynchronised or refusing "
                       "(kiss-of-death); reference id %r"
                       % data[12:16].decode("ascii", "replace"))
    ref_sec, ref_frac = _unpack_timestamp(data, 16)
    origin = _unpack_timestamp(data, 24)
    receive = _unpack_timestamp(data, 32)
    transmit = _unpack_timestamp(data, 40)
    if expected_origin is not None and origin != expected_origin:
        raise NtpError("origin timestamp mismatch: response does not match "
                       "this request")
    return {
        "leap_indicator": leap,
        "version": version,
        "mode": mode,
        "stratum": stratum,
        "poll": data[2],
        "precision": struct.unpack_from(">b", data, 3)[0],
        "root_delay": struct.unpack_from(">i", data, 4)[0] / 65536.0,
        "root_dispersion": struct.unpack_from(">I", data, 8)[0] / 65536.0,
        "reference_id": data[12:16],
        "reference_timestamp": ntp_to_unix(ref_sec, ref_frac),
        "origin_timestamp": ntp_to_unix(*origin),
        "receive_timestamp": ntp_to_unix(*receive),
        "transmit_timestamp": ntp_to_unix(*transmit),
        "origin_ntp": origin,
        "receive_ntp": receive,
        "transmit_ntp": transmit,
    }


def compute_offset_delay(t0, t1, t2, t3):
    """Offset theta and round-trip delay delta, per the challenge page.

    theta = ((t1 - t0) + (t2 - t3)) / 2
    delta = (t3 - t0) - (t2 - t1)
    All four times are Unix timestamps in seconds.
    """
    offset = ((t1 - t0) + (t2 - t3)) / 2.0
    delay = (t3 - t0) - (t2 - t1)
    return offset, delay


def query(host, port=NTP_PORT, timeout=5.0):
    """Send one request to host:port and return the full measurement dict.

    t0 is captured just before send, t3 just after receive, so the delay
    includes the local send/receive path, as in a real client.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        # t0 is the transmit timestamp itself, so the packet field and the
        # offset/delay computation use exactly the same instant.
        t0 = time.time()
        request, transmit_ntp = build_request(t0)
        sock.sendto(request, (host, port))
        data, _addr = sock.recvfrom(512)
        t3 = time.time()
    except socket.timeout:
        raise NtpError("timed out after %.1f s waiting for %s:%d"
                       % (timeout, host, port))
    except OSError as exc:
        raise NtpError("UDP error talking to %s:%d: %s" % (host, port, exc))
    finally:
        sock.close()
    parsed = parse_response(data, expected_origin=transmit_ntp)
    offset, delay = compute_offset_delay(
        t0, parsed["receive_timestamp"], parsed["transmit_timestamp"], t3)
    parsed.update({
        "host": host,
        "port": port,
        "client_send_timestamp": t0,
        "client_receive_timestamp": t3,
        "offset_seconds": offset,
        "delay_seconds": delay,
        "server_time": parsed["transmit_timestamp"],
        "corrected_local_time": t3 + offset,
    })
    return parsed


def format_result(result, as_json=False):
    if as_json:
        out = {k: v for k, v in result.items()
               if k not in ("origin_ntp", "receive_ntp", "transmit_ntp")}
        out["reference_id"] = result["reference_id"].decode("ascii", "replace")
        for key in ("client_send_timestamp", "client_receive_timestamp",
                    "origin_timestamp", "receive_timestamp",
                    "transmit_timestamp", "reference_timestamp",
                    "server_time", "corrected_local_time"):
            out[key + "_iso"] = datetime.datetime.fromtimestamp(
                out[key], datetime.timezone.utc).isoformat()
        return json.dumps(out, indent=2, sort_keys=True)
    lines = [
        "NTP server: %s:%d  (stratum %d, version %d, leap %d)"
        % (result["host"], result["port"], result["stratum"],
           result["version"], result["leap_indicator"]),
        "t0 client send:    %.6f" % result["client_send_timestamp"],
        "t1 server receive: %.6f" % result["receive_timestamp"],
        "t2 server send:    %.6f" % result["transmit_timestamp"],
        "t3 client receive: %.6f" % result["client_receive_timestamp"],
        "Offset: %.6f s  (server - local; add this to local time)"
        % result["offset_seconds"],
        "Round-trip delay: %.6f s" % result["delay_seconds"],
        "Server time: %s"
        % datetime.datetime.fromtimestamp(
            result["server_time"], datetime.timezone.utc).isoformat(),
        "Corrected local time (not applied): %s"
        % datetime.datetime.fromtimestamp(
            result["corrected_local_time"], datetime.timezone.utc).isoformat(),
        "NOTE: the system clock was NOT changed. See docs/SPEC.md Step 4.",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="NTP client: query one NTP server and report offset/delay.")
    parser.add_argument("host", nargs="?", default="pool.ntp.org",
                        help="NTP server hostname/IP (default: pool.ntp.org)")
    parser.add_argument("--port", type=int, default=NTP_PORT)
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="seconds to wait for a response (default 5)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    args = parser.parse_args(argv)
    try:
        result = query(args.host, port=args.port, timeout=args.timeout)
    except NtpError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    print(format_result(result, as_json=args.json))
    return 0


if __name__ == "__main__":
    sys.exit(main())
