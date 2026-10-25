#!/usr/bin/env python3
"""TCP connect (vanilla) port scanner.

Build Your Own Port Scanner (codingchallenges.fyi, slug
``challenge-port-scanner``), Steps 1-4: single-port scan, vanilla
1-65535 scan, timeout + concurrency, and sweep scans over a host
list, wildcard, or CIDR range. Python 3 standard library only.

Port states: ``open`` (connect succeeds), ``closed`` (refused),
``filtered`` (connect times out), ``error`` (e.g. DNS failure).

Only scan hosts you own or have explicit permission to scan.
"""

import argparse
import concurrent.futures
import ipaddress
import socket
import sys

MIN_PORT = 1
MAX_PORT = 65535
DEFAULT_TIMEOUT = 0.5
DEFAULT_WORKERS = 100


def scan_port(host, port, timeout=DEFAULT_TIMEOUT):
    """Scan one TCP port; return 'open', 'closed', 'filtered' or 'error'."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "open"
    except socket.gaierror:
        return "error"
    except ConnectionRefusedError:
        return "closed"
    except (socket.timeout, TimeoutError):
        return "filtered"
    except OSError:
        # Unreachable network etc.: not a clean refused/timeout, so
        # report it distinctly rather than mislabelling it.
        return "error"


def parse_ports(spec):
    """Parse '80', '80,443', '1-1024', '80,8000-8010' -> sorted list.

    Raises ValueError on any invalid part (out of 1-65535, reversed
    range, empty, non-numeric).
    """
    ports = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise ValueError("empty port in %r" % spec)
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            try:
                start, end = int(start_s), int(end_s)
            except ValueError:
                raise ValueError("invalid port range %r" % part) from None
            if start < MIN_PORT or end > MAX_PORT or start > end:
                raise ValueError("invalid port range %r" % part)
            ports.update(range(start, end + 1))
        else:
            try:
                port = int(part)
            except ValueError:
                raise ValueError("invalid port %r" % part) from None
            if port < MIN_PORT or port > MAX_PORT:
                raise ValueError("port %d out of range 1-65535" % port)
            ports.add(port)
    if not ports:
        raise ValueError("no ports in %r" % spec)
    return sorted(ports)


def expand_hosts(spec):
    """Expand a host spec -> list of hosts.

    Single host passes through; comma-separated lists split; a
    trailing '.*' wildcard expands to .1-.254; CIDR expands to its
    host addresses. CIDR prefixes shorter than /24 are rejected:
    expanding them would sweep thousands of hosts.
    """
    hosts = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            raise ValueError("empty host in %r" % spec)
        if item.endswith(".*"):
            base = item[:-2]
            if not base or base.count(".") != 2:
                raise ValueError("wildcard must be like 192.168.1.*")
            hosts.extend("%s.%d" % (base, i) for i in range(1, 255))
        elif "/" in item:
            try:
                network = ipaddress.ip_network(item, strict=False)
            except ValueError:
                raise ValueError("invalid CIDR %r" % item) from None
            if network.prefixlen < 24:
                raise ValueError(
                    "CIDR %r too large (prefix must be /24 or longer)" % item
                )
            hosts.extend(str(addr) for addr in network.hosts())
        else:
            hosts.append(item)
    return hosts


def scan_host(host, ports, timeout=DEFAULT_TIMEOUT, workers=DEFAULT_WORKERS):
    """Scan ports on one host concurrently; return {port: state}."""
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(scan_port, host, port, timeout): port for port in ports
        }
        for future in concurrent.futures.as_completed(futures):
            results[futures[future]] = future.result()
    return results


def _port_type(value):
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer") from None
    if port < MIN_PORT or port > MAX_PORT:
        raise argparse.ArgumentTypeError("port must be 1-65535")
    return port


def _ports_type(value):
    try:
        return parse_ports(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def _hosts_type(value):
    try:
        return expand_hosts(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def build_parser():
    parser = argparse.ArgumentParser(
        description="TCP connect port scanner (Steps 1-4)."
    )
    parser.add_argument("--host", required=True, type=_hosts_type,
                        help="host, comma list, wildcard (192.168.1.*) or CIDR")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--port", type=_port_type,
                       help="single port to scan (Step 1)")
    group.add_argument("--ports", type=_ports_type,
                       help="ports: 80, 80,443, 1-1024, 80,8000-8010")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="connect timeout in seconds (default 0.5)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="concurrent ports (default 100)")
    parser.add_argument("--show-all", action="store_true",
                        help="also print closed/filtered ports, not just open")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.timeout <= 0:
        print("error: --timeout must be positive", file=sys.stderr)
        return 2
    if args.workers < 1:
        print("error: --workers must be at least 1", file=sys.stderr)
        return 2
    if args.port is not None:
        ports = [args.port]
    elif args.ports is not None:
        ports = args.ports
    else:
        ports = list(range(MIN_PORT, MAX_PORT + 1))

    exit_code = 0
    for host in args.host:
        if args.port is not None:
            print("Scanning host: %s port: %d" % (host, args.port))
        else:
            print("Scanning host: %s" % host)
        results = scan_host(host, ports, args.timeout, args.workers)
        open_count = 0
        for port in sorted(results):
            state = results[port]
            if state == "open":
                open_count += 1
                print("Port: %d is open" % port)
            elif args.show_all:
                print("Port: %d is %s" % (port, state))
            if state == "error":
                exit_code = 1
        print("Summary for %s: %d open / %d scanned"
              % (host, open_count, len(ports)))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
