#!/usr/bin/env python3
"""whois — a minimal WHOIS client (RFC 3912).

Queries a whois server on port 43, parses the Key: Value response
(dropping blank lines and '%' comments), and follows referrals
(IANA's `refer` field, then a registry's `Registrar WHOIS Server`
field) until a response carries no referral. Works for domain
names, IP addresses and AS numbers through the same code path.

Standard library only. Usage: python3 whois.py example.com
"""

import argparse
import re
import socket
import sys

DEFAULT_SERVER = "whois.iana.org"
DEFAULT_PORT = 43
DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_HOPS = 5

# Referral fields, in priority order (keys are lower-cased by parse).
REFERRAL_KEYS = ("refer", "registrar whois server", "whois server", "whois")


def query(server, query_text, port=DEFAULT_PORT, timeout=DEFAULT_TIMEOUT):
    """One RFC 3912 exchange: send ``query_text + CRLF``, read to EOF."""
    with socket.create_connection((server, port), timeout=timeout) as sock:
        sock.sendall(query_text.encode("utf-8") + b"\r\n")
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


def parse_whois(text):
    """Parse a whois response into {lower-cased key: [values]}.

    Blank lines and '%' comment lines are dropped. Lines are split
    on the first colon only, so values containing colons survive.
    Repeated keys accumulate in order. A colon-less line is
    appended to the previous value; one with no predecessor is
    dropped.
    """
    parsed = {}
    last_key = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("%"):
            continue
        if ":" not in line:
            if last_key is not None:
                parsed[last_key][-1] += " " + line
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        parsed.setdefault(key, []).append(value)
        last_key = key
    return parsed


def _strip_referral(value):
    """Normalise a referral value to a bare hostname.

    Real referrals are bare hostnames; a scheme (whois://host) or a
    trailing :port is stripped defensively. The port is ignored:
    --port applies to every hop.
    """
    value = value.strip()
    value = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", value)
    value = value.split("/")[0]
    if value.startswith("["):  # IPv6 literal [::1]:port
        host = value.split("]")[0] + "]"
        return host.strip("[]")
    return value.split(":")[0].strip()


def find_referral(parsed):
    """Return the next whois server hostname, or None."""
    for key in REFERRAL_KEYS:
        for value in parsed.get(key, []):
            if value.strip():
                host = _strip_referral(value)
                if host:
                    return host
    return None


def lookup(query_text, server=DEFAULT_SERVER, port=DEFAULT_PORT,
           timeout=DEFAULT_TIMEOUT, max_hops=DEFAULT_MAX_HOPS,
           follow=True):
    """Follow the referral chain; return [(server, response), ...]."""
    hops = []
    visited = set()
    current = server
    for _ in range(max_hops):
        response = query(current, query_text, port=port, timeout=timeout)
        hops.append((current, response))
        if not follow:
            break
        visited.add(current.lower())
        referral = find_referral(parse_whois(response))
        if referral is None or referral.lower() in visited:
            break
        current = referral
    return hops


def format_parsed(parsed):
    """Render parsed data as 'key: value' lines, one per value."""
    lines = []
    for key, values in parsed.items():
        for value in values:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + ("\n" if lines else "")


def _valid_query(query_text):
    return bool(query_text) and not re.search(r"\s", query_text)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Query a whois server (port 43) and follow referrals.")
    parser.add_argument("query", nargs="?", help="domain, IP address or AS")
    parser.add_argument("--server", default=DEFAULT_SERVER,
                        help="first whois server (default: %(default)s)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="port for every hop (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="seconds per query (default: %(default)s)")
    parser.add_argument("--max-hops", type=int, default=DEFAULT_MAX_HOPS,
                        help="max servers to query (default: %(default)s)")
    parser.add_argument("--no-follow", action="store_true",
                        help="query only the first server")
    parser.add_argument("--parsed", action="store_true",
                        help="print parsed key/value lines, not raw text")
    args = parser.parse_args(argv)

    if not args.query or not _valid_query(args.query):
        print("error: provide one query (domain, IP or AS, no whitespace)",
              file=sys.stderr)
        return 2
    if args.max_hops < 1 or args.port < 1 or args.port > 65535:
        print("error: --max-hops must be >= 1 and --port in 1..65535",
              file=sys.stderr)
        return 2
    try:
        hops = lookup(args.query, server=args.server, port=args.port,
                      timeout=args.timeout, max_hops=args.max_hops,
                      follow=not args.no_follow)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    out = []
    for _server, response in hops:
        text = format_parsed(parse_whois(response)) if args.parsed else response
        out.append(text if text.endswith("\n") or not text else text + "\n")
    sys.stdout.write("".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
