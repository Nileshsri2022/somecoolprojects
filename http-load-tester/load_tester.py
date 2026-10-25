#!/usr/bin/env python3
"""HTTP(S) load tester — Coding Challenges: Build Your Own HTTP(S)
Load Tester (https://codingchallenges.fyi/challenges/challenge-load-tester/).

Python 3 standard library only. Fires N concurrent HTTP(S) requests
at a URL (or URLs cycled from a file), records per-request timings
(total, time to first byte, time to last byte) and status codes,
and prints a summary in the challenge's Step 5 form.

Usage:
    python3 load_tester.py [URL] [-u URL] [-n N] [-c C] [-f FILE]
                           [-d SECONDS] [-X METHOD] [--timeout SECONDS]
                           [--insecure]

Single request (-n 1, no -d): prints "Response code: 200" (Steps 1-2).
Otherwise prints a "Results:" summary (Steps 3-5).
Only test targets you own or have permission to test.
"""

import argparse
import http.client
import math
import ssl
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlsplit

USER_AGENT = "ccload/1.0"


@dataclass
class RequestResult:
    url: str
    status: int | None  # None => no HTTP response (network error)
    total: float | None = None  # start -> body fully read (seconds)
    ttfb: float | None = None   # start -> headers received (seconds)
    ttlb: float | None = None   # headers -> body fully read (seconds)
    error: str | None = None


def compute_stats(values):
    """Min/max/mean/p50/p90/p99 of a list of floats (nearest-rank
    percentiles). All fields None for an empty list."""
    if not values:
        return {"min": None, "max": None, "mean": None,
                "p50": None, "p90": None, "p99": None}
    ordered = sorted(values)
    n = len(ordered)

    def percentile(p):
        rank = math.ceil(p / 100.0 * n)
        return ordered[max(1, rank) - 1]

    return {"min": ordered[0], "max": ordered[-1],
            "mean": sum(ordered) / n,
            "p50": percentile(50), "p90": percentile(90),
            "p99": percentile(99)}


@dataclass
class Summary:
    results: list = field(default_factory=list)
    wall_time: float = 0.0
    total: int = 0
    successes: int = 0  # 2XX
    failures: int = 0   # non-2XX + errors
    failed_5xx: int = 0
    status_counts: dict = field(default_factory=dict)
    error_count: int = 0
    requests_per_second: float = 0.0
    total_stats: dict = field(default_factory=dict)
    ttfb_stats: dict = field(default_factory=dict)
    ttlb_stats: dict = field(default_factory=dict)


def summarise(results, wall_time):
    """Aggregate per-request results into a Summary."""
    s = Summary(results=results, wall_time=wall_time, total=len(results))
    s.status_counts = dict(Counter(r.status for r in results
                                   if r.status is not None))
    s.error_count = sum(1 for r in results if r.error is not None)
    for code, count in s.status_counts.items():
        if 200 <= code < 300:
            s.successes += count
        if 500 <= code < 600:
            s.failed_5xx += count
    s.failures = s.total - s.successes
    s.requests_per_second = s.total / wall_time if wall_time > 0 else 0.0
    done = [r for r in results if r.status is not None]
    s.total_stats = compute_stats([r.total for r in done
                                   if r.total is not None])
    s.ttfb_stats = compute_stats([r.ttfb for r in done
                                  if r.ttfb is not None])
    s.ttlb_stats = compute_stats([r.ttlb for r in done
                                  if r.ttlb is not None])
    return s


def _fmt_stats(stats):
    if stats["min"] is None:
        return "n/a"
    return f"{stats['min']:.3f}, {stats['max']:.3f}, {stats['mean']:.3f}"


def format_summary(summary):
    """The challenge's Step 5 layout, plus successes/failures,
    percentiles, per-code breakdown and error count."""
    lines = ["Results:",
             f" Total Requests (2XX).......................: "
             f"{summary.successes}",
             f" Failed Requests (5XX)......................: "
             f"{summary.failed_5xx}",
             f" Successes..................................: "
             f"{summary.successes}",
             f" Failures...................................: "
             f"{summary.failures}",
             f" Total Requests.............................: "
             f"{summary.total}",
             f" Request/second.............................: "
             f"{summary.requests_per_second:.2f}",
             f"Total Request Time (s) (Min, Max, Mean).....: "
             f"{_fmt_stats(summary.total_stats)}",
             f"Time to First Byte (s) (Min, Max, Mean).....: "
             f"{_fmt_stats(summary.ttfb_stats)}",
             f"Time to Last Byte (s) (Min, Max, Mean)......: "
             f"{_fmt_stats(summary.ttlb_stats)}"]
    p = summary.total_stats
    if p["p50"] is None:
        lines.append("Total Request Time percentiles (s) (p50, p90, p99): "
                     "n/a")
    else:
        lines.append(f"Total Request Time percentiles (s) (p50, p90, p99): "
                     f"{p['p50']:.3f}, {p['p90']:.3f}, {p['p99']:.3f}")
    if summary.status_counts:
        breakdown = ", ".join(f"{code}: {count}" for code, count in
                              sorted(summary.status_counts.items()))
    else:
        breakdown = "none"
    lines.append(f"Status codes...............................: {breakdown}")
    lines.append(f"Errors.....................................: "
                 f"{summary.error_count}")
    return "\n".join(lines)


def validate_url(url):
    """Return an error string for an unusable URL, else None."""
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        return str(exc)
    if parts.scheme not in ("http", "https"):
        return f"unsupported scheme in URL: {url!r} (want http/https)"
    if not parts.netloc:
        return f"missing host in URL: {url!r}"
    return None


def do_request(url, method="GET", timeout=30, insecure=False):
    """One request. 4XX/5XX/3XX are normal results, not exceptions;
    only transport failures become error results."""
    err = validate_url(url)
    if err is not None:
        return RequestResult(url=url, status=None, error=err)
    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    host = parts.hostname
    port = parts.port  # None => scheme default, handled by http.client
    start = time.monotonic()
    conn = None
    try:
        if parts.scheme == "https":
            context = (ssl._create_unverified_context() if insecure
                       else ssl.create_default_context())
            conn = http.client.HTTPSConnection(host, port,
                                               timeout=timeout,
                                               context=context)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request(method, path,
                     headers={"User-Agent": USER_AGENT,
                              "Accept": "*/*",
                              "Connection": "close"})
        resp = conn.getresponse()
        ttfb = time.monotonic() - start
        resp.read()  # drain body; discards it, we only measure
        end = time.monotonic()
        return RequestResult(url=url, status=resp.status,
                             total=end - start, ttfb=ttfb,
                             ttlb=end - start - ttfb)
    except Exception as exc:  # transport failure: record, don't raise
        return RequestResult(url=url, status=None, error=str(exc))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def run_load(urls, count=None, concurrency=1, duration=None,
             method="GET", timeout=30, insecure=False):
    """Run the load test. count=None means unlimited (requires a
    duration). Returns a Summary. Exactly `count` results for a
    count run; a duration run stops claiming new requests after the
    deadline (in-flight requests finish)."""
    if not urls:
        raise ValueError("no URLs to test")
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    if count is not None and count < 1:
        raise ValueError("request count must be >= 1")
    if duration is not None and duration <= 0:
        raise ValueError("duration must be > 0")
    if count is None and duration is None:
        raise ValueError("need a request count or a duration")
    deadline = (time.monotonic() + duration) if duration else None
    results = []
    results_lock = threading.Lock()
    state_lock = threading.Lock()
    next_index = [0]

    def worker():
        while True:
            with state_lock:
                if deadline is not None and time.monotonic() >= deadline:
                    return
                if count is not None and next_index[0] >= count:
                    return
                index = next_index[0]
                next_index[0] += 1
            result = do_request(urls[index % len(urls)], method=method,
                                timeout=timeout, insecure=insecure)
            with results_lock:
                results.append(result)

    start = time.monotonic()
    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return summarise(results, time.monotonic() - start)


def load_urls_file(path):
    """URLs from a file: one per line, blank lines skipped."""
    with open(path, encoding="utf-8") as f:
        urls = [line.strip() for line in f]
    return [u for u in urls if u]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="load_tester.py",
        description="HTTP(S) load tester: concurrent requests with "
                    "latency statistics and a status-code breakdown.")
    parser.add_argument("url", nargs="?", help="URL to test (Step 1)")
    parser.add_argument("-u", "--url", dest="opt_url",
                        help="URL to test")
    parser.add_argument("-n", "--requests", type=int, default=None,
                        help="number of requests (default: 10, or 1 "
                             "for a bare positional URL)")
    parser.add_argument("-c", "--concurrency", type=int, default=1,
                        help="concurrent requests (default: 1)")
    parser.add_argument("-f", "--file", dest="url_file",
                        help="file with one URL per line; URLs are "
                             "cycled round-robin")
    parser.add_argument("-d", "--duration", type=float, default=None,
                        help="stop starting new requests after this "
                             "many seconds")
    parser.add_argument("-X", "--method", default="GET",
                        help="HTTP method (default: GET)")
    parser.add_argument("--timeout", type=float, default=30,
                        help="per-request timeout in seconds "
                             "(default: 30)")
    parser.add_argument("--insecure", action="store_true",
                        help="skip TLS certificate verification")
    args = parser.parse_args(argv)
    # -n stays None here so main() can tell "user gave no -n" from
    # "user gave -n 10": with -d and no -n the count is unlimited,
    # with a bare positional URL and no -n it is the Step 1 single
    # request, otherwise the page default of 10 applies.
    return args


def main(argv=None):
    args = parse_args(argv)
    urls = []
    if args.url_file:
        try:
            urls = load_urls_file(args.url_file)
        except OSError as exc:
            print(f"error: cannot read URL file: {exc}", file=sys.stderr)
            return 2
        if not urls:
            print("error: URL file is empty", file=sys.stderr)
            return 2
    elif args.opt_url or args.url:
        urls = [args.opt_url or args.url]
    else:
        print("error: no URL given (positional URL, -u, or -f required)",
              file=sys.stderr)
        return 2
    for url in urls:
        err = validate_url(url)
        if err is not None:
            print(f"error: {err}", file=sys.stderr)
            return 2
    if args.concurrency < 1:
        print("error: -c must be >= 1", file=sys.stderr)
        return 2
    if args.duration is not None and args.duration <= 0:
        print("error: -d must be > 0", file=sys.stderr)
        return 2
    if args.requests is not None and args.requests < 1:
        print("error: -n must be >= 1", file=sys.stderr)
        return 2
    # Resolve the effective count (see parse_args).
    if args.requests is not None:
        count = args.requests
    elif args.duration is not None:
        count = None  # unlimited until the deadline
    elif args.url is not None:
        count = 1  # Step 1 single-request form
    else:
        count = 10  # page default
    if args.duration is None and count == 1 \
            and len(urls) == 1 and args.concurrency == 1:
        # Steps 1-2 single-request form.
        result = do_request(urls[0], method=args.method,
                            timeout=args.timeout, insecure=args.insecure)
        if result.error is not None:
            print(f"Error: {result.error}", file=sys.stderr)
            return 1
        print(f"Response code: {result.status}")
        return 0
    # With a duration, -n is a cap, not a requirement: run_load stops
    # at whichever limit comes first, which is exactly that behaviour.
    summary = run_load(urls, count=count, concurrency=args.concurrency,
                       duration=args.duration, method=args.method,
                       timeout=args.timeout, insecure=args.insecure)
    print(format_summary(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
