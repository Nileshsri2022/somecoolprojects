#!/usr/bin/env python3
"""Uptime Monitoring Service — CLI monitor (Python 3 standard library only).

Monitors URLs on a schedule (HTTP HEAD by default, GET on request),
records up/down history with latency (TTFB + total for GET), prints
historical reports with an ASCII latency graph, exports history as
JSON/CSV, and fires alerts after N consecutive failures or when a
target is too slow (log file, webhook POST, email-hook file).

See docs/SPEC.md for the challenge-step coverage and divergences.
"""

import argparse
import csv
import http.client
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DEFAULT_STORE = "uptime-store.json"
DEFAULT_INTERVAL = 60
DEFAULT_ALERT_AFTER = 3
CHECK_TIMEOUT = 10.0
WEBHOOK_TIMEOUT = 5.0
SPARK_CHARS = "▁▂▃▄▅▆▇█"


class MonitorError(Exception):
    """User-facing error: printed to stderr, exit code non-zero."""


# ---------------------------------------------------------------- store

def empty_store():
    return {"targets": [], "checks": [], "alerts": [], "state": {}}


def load_store(path):
    if not os.path.exists(path):
        return empty_store()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise MonitorError(f"store file {path!r} is corrupt: {exc}") from exc
    if not isinstance(data, dict) or "targets" not in data:
        raise MonitorError(f"store file {path!r} has an unexpected format")
    data.setdefault("checks", [])
    data.setdefault("alerts", [])
    data.setdefault("state", {})
    return data


def save_store(path, store):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=2)
    os.replace(tmp, path)


def validate_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise MonitorError(
            f"invalid URL {url!r}: expected http(s)://host[/path]")
    return url


def find_target(store, url):
    for target in store["targets"]:
        if target["url"] == url:
            return target
    return None


def add_target(store, url, interval=DEFAULT_INTERVAL, method="HEAD",
               slow_threshold_ms=None, alert_after=DEFAULT_ALERT_AFTER,
               alert_log=None, webhook=None, email_hook=None):
    validate_url(url)
    if interval < 1:
        raise MonitorError("interval must be at least 1 second")
    method = method.upper()
    if method not in ("HEAD", "GET"):
        raise MonitorError(f"unsupported method {method!r}: use HEAD or GET")
    if alert_after < 1:
        raise MonitorError("alert-after must be at least 1")
    if find_target(store, url) is not None:
        raise MonitorError(f"target {url!r} is already monitored")
    target = {
        "url": url,
        "interval_seconds": interval,
        "method": method,
        "slow_threshold_ms": slow_threshold_ms,
        "alert_after": alert_after,
        "alert_log": alert_log,
        "webhook": webhook,
        "email_hook": email_hook,
    }
    store["targets"].append(target)
    store["state"].setdefault(url, {"consecutive_failures": 0,
                                    "alerting": False})
    return target


def remove_target(store, url):
    target = find_target(store, url)
    if target is None:
        raise MonitorError(f"no monitored target {url!r}")
    store["targets"].remove(target)
    store["state"].pop(url, None)
    return target


# ---------------------------------------------------------------- checks

def check_head(url):
    """HEAD check via http.client: returns (status, latency_ms, error)."""
    parsed = urllib.parse.urlparse(url)
    host, port = parsed.hostname, parsed.port
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    conn_cls = (http.client.HTTPSConnection if parsed.scheme == "https"
                else http.client.HTTPConnection)
    kwargs = {"timeout": CHECK_TIMEOUT}
    if parsed.scheme == "https":
        kwargs["context"] = ssl.create_default_context()
    conn = conn_cls(host, port, **kwargs)
    start = time.monotonic()
    try:
        conn.request("HEAD", path)
        resp = conn.getresponse()
        resp.read()  # HEAD has no body, but drain defensively
        latency = (time.monotonic() - start) * 1000.0
        return resp.status, latency, None
    except Exception as exc:  # noqa: BLE001 — any transport failure = down
        return None, (time.monotonic() - start) * 1000.0, str(exc)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001, S110 — best effort
            pass


def check_get(url):
    """GET check: returns (status, ttfb_ms, total_ms, error).

    TTFB = time to first byte read; total = time to end of body.
    """
    req = urllib.request.Request(url, method="GET")
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT) as resp:
            first = resp.read(1)
            ttfb = (time.monotonic() - start) * 1000.0
            if first:
                resp.read()
            total = (time.monotonic() - start) * 1000.0
            return resp.status, ttfb, total, None
    except urllib.error.HTTPError as exc:
        total = (time.monotonic() - start) * 1000.0
        try:
            exc.read()
        except Exception:  # noqa: BLE001, S110 — best effort
            pass
        return exc.code, total, total, None
    except Exception as exc:  # noqa: BLE001 — any transport failure = down
        total = (time.monotonic() - start) * 1000.0
        return None, None, total, str(exc)


def perform_check(target):
    """Run one check for a target; returns a check record dict."""
    url, method = target["url"], target.get("method", "HEAD")
    now = datetime.now(timezone.utc).isoformat()
    if method == "GET":
        status, ttfb, total, error = check_get(url)
        latency = total
    else:
        status, latency, error = check_head(url)
        ttfb, total = None, latency
    ok = error is None and status is not None and 200 <= status < 400
    return {
        "url": url,
        "timestamp": now,
        "status": status,
        "ok": ok,
        "latency_ms": round(latency, 2) if latency is not None else None,
        "ttfb_ms": round(ttfb, 2) if ttfb is not None else None,
        "total_ms": round(total, 2) if total is not None else None,
        "method": method,
        "error": error,
    }


# ---------------------------------------------------------------- alerts

def emit_alert(store, target, kind, message, failures=None):
    event = {
        "url": target["url"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "message": message,
        "consecutive_failures": failures,
    }
    store["alerts"].append(event)
    line = f"{event['timestamp']} [{kind}] {target['url']}: {message}\n"
    if target.get("alert_log"):
        try:
            with open(target["alert_log"], "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass
    if target.get("email_hook"):
        try:
            with open(target["email_hook"], "a", encoding="utf-8") as fh:
                fh.write(f"Subject: Uptime alert [{kind}] {target['url']}\n"
                         f"{message}\n---\n")
        except OSError:
            pass
    if target.get("webhook"):
        try:
            req = urllib.request.Request(
                target["webhook"],
                data=json.dumps(event).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=WEBHOOK_TIMEOUT) as resp:
                resp.read()
        except Exception:  # noqa: BLE001, S110 — failing sink never fails check
            pass
    return event


def evaluate_alerts(store, target, check):
    """Update incident state and emit DOWN/SLOW/RECOVERY alerts."""
    state = store["state"].setdefault(
        target["url"], {"consecutive_failures": 0, "alerting": False})
    emitted = []
    if not check["ok"]:
        state["consecutive_failures"] += 1
        if (state["consecutive_failures"] >= target.get("alert_after", 3)
                and not state["alerting"]):
            state["alerting"] = True
            emitted.append(emit_alert(
                store, target, "DOWN",
                f"down after {state['consecutive_failures']} consecutive "
                f"failed checks (last status: {check['status']}, "
                f"error: {check['error']})",
                failures=state["consecutive_failures"]))
    else:
        if state["alerting"]:
            state["alerting"] = False
            state["consecutive_failures"] = 0
            emitted.append(emit_alert(
                store, target, "RECOVERY",
                f"back up (status {check['status']}, "
                f"latency {check['latency_ms']} ms)"))
        else:
            state["consecutive_failures"] = 0
        threshold = target.get("slow_threshold_ms")
        latency = check["latency_ms"]
        if threshold and latency is not None and latency > threshold:
            emitted.append(emit_alert(
                store, target, "SLOW",
                f"slow response: {latency} ms exceeds threshold "
                f"{threshold} ms"))
    return emitted


def run_check_cycle(store):
    """Check every target once; returns (checks, alerts)."""
    checks, alerts = [], []
    for target in store["targets"]:
        try:
            check = perform_check(target)
        except Exception as exc:  # noqa: BLE001 — one bad target never blocks others
            check = {
                "url": target["url"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": None, "ok": False, "latency_ms": None,
                "ttfb_ms": None, "total_ms": None,
                "method": target.get("method", "HEAD"), "error": str(exc),
            }
        store["checks"].append(check)
        checks.append(check)
        alerts.extend(evaluate_alerts(store, target, check))
    return checks, alerts


# ---------------------------------------------------------------- reports

def parse_time(value):
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MonitorError(f"invalid ISO-8601 time {value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def filter_checks(store, url=None, from_time=None, to_time=None):
    out = []
    for check in store["checks"]:
        if url and check["url"] != url:
            continue
        ts = parse_time(check["timestamp"])
        if from_time and ts < from_time:
            continue
        if to_time and ts > to_time:
            continue
        out.append(check)
    return out


def sparkline(values):
    if not values:
        return ""
    top = max(values)
    if top <= 0:
        return SPARK_CHARS[0] * len(values)
    return "".join(SPARK_CHARS[min(7, int(v / top * 7))] for v in values)


def report_text(checks):
    lines = []
    if not checks:
        return "No checks in range.\nUptime: n/a\n"
    total = len(checks)
    up = sum(1 for c in checks if c["ok"])
    lat = [c["latency_ms"] for c in checks if c["latency_ms"] is not None]
    lines.append(f"Checks: {total}  Up: {up}  Down: {total - up}")
    lines.append(f"Uptime: {up / total * 100:.1f}%")
    if lat:
        lines.append(f"Latency ms: avg {sum(lat) / len(lat):.1f}  "
                     f"min {min(lat):.1f}  max {max(lat):.1f}")
        lines.append(f"Latency graph: {sparkline(lat)}")
    ttfb = [c["ttfb_ms"] for c in checks
            if c.get("ttfb_ms") is not None]
    if ttfb:
        lines.append(f"TTFB ms: avg {sum(ttfb) / len(ttfb):.1f}")
    lines.append("")
    lines.append(f"{'TIME':<26} {'METHOD':<6} {'STATUS':<7} {'OK':<4} "
                 f"{'LATENCY_MS':>10}  URL")
    for c in checks:
        lines.append(f"{c['timestamp']:<26} {c['method']:<6} "
                     f"{str(c['status']):<7} {str(c['ok']):<4} "
                     f"{c['latency_ms'] if c['latency_ms'] is not None else '-':>10}  "
                     f"{c['url']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- CLI

def build_parser():
    parser = argparse.ArgumentParser(description="Uptime Monitoring Service")
    parser.add_argument("--store", default=DEFAULT_STORE,
                        help="store file (default: uptime-store.json)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="add a URL to monitor")
    p.add_argument("--url", required=True)
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    p.add_argument("--method", default="HEAD")
    p.add_argument("--slow-threshold-ms", type=float, default=None)
    p.add_argument("--alert-after", type=int, default=DEFAULT_ALERT_AFTER)
    p.add_argument("--alert-log", default=None)
    p.add_argument("--webhook", default=None)
    p.add_argument("--email-hook", default=None)

    sub.add_parser("list", help="list monitored targets")
    p = sub.add_parser("remove", help="stop monitoring a URL")
    p.add_argument("--url", required=True)

    p = sub.add_parser("check", help="one immediate check cycle")
    p.add_argument("--url", default=None)

    p = sub.add_parser("run", help="monitor loop until stopped")
    p.add_argument("--cycles", type=int, default=None)
    p.add_argument("--max-seconds", type=float, default=None)

    p = sub.add_parser("report", help="historical uptime/latency report")
    p.add_argument("--url", default=None)
    p.add_argument("--from", dest="from_time", default=None)
    p.add_argument("--to", dest="to_time", default=None)

    p = sub.add_parser("export", help="export history as JSON or CSV")
    p.add_argument("--url", default=None)
    p.add_argument("--format", choices=["json", "csv"], required=True)
    p.add_argument("--out", required=True)

    p = sub.add_parser("alerts", help="show recorded alert events")
    p.add_argument("--url", default=None)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        store = load_store(args.store)
    except MonitorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        if args.command == "add":
            target = add_target(store, args.url, interval=args.interval,
                                method=args.method,
                                slow_threshold_ms=args.slow_threshold_ms,
                                alert_after=args.alert_after,
                                alert_log=args.alert_log,
                                webhook=args.webhook,
                                email_hook=args.email_hook)
            save_store(args.store, store)
            print(f"Added {target['url']} (every {target['interval_seconds']}s, "
                  f"{target['method']})")
        elif args.command == "list":
            if not store["targets"]:
                print("No targets monitored.")
            for t in store["targets"]:
                print(f"{t['url']}  every {t['interval_seconds']}s  "
                      f"{t['method']}  alert_after={t['alert_after']}")
        elif args.command == "remove":
            remove_target(store, args.url)
            save_store(args.store, store)
            print(f"Removed {args.url}")
        elif args.command == "check":
            subset = store
            if args.url:
                target = find_target(store, args.url)
                if target is None:
                    raise MonitorError(f"no monitored target {args.url!r}")
                subset = {"targets": [target], "checks": [],
                          "alerts": [], "state": store["state"]}
                checks, alerts = run_check_cycle(subset)
                store["checks"].extend(checks)
                store["alerts"].extend(alerts)
                store["state"].update(subset["state"])
            else:
                checks, alerts = run_check_cycle(store)
            save_store(args.store, store)
            for c in checks:
                print(f"{c['url']}: {'UP' if c['ok'] else 'DOWN'} "
                      f"(status {c['status']}, {c['latency_ms']} ms)")
            for a in alerts:
                print(f"ALERT [{a['kind']}] {a['url']}: {a['message']}")
        elif args.command == "run":
            last_check = {}
            cycles = 0
            started = time.monotonic()
            try:
                while True:
                    now = time.monotonic()
                    due = [t for t in store["targets"]
                           if now - last_check.get(t["url"], 0)
                           >= t["interval_seconds"]
                           or t["url"] not in last_check]
                    if due:
                        subset = {"targets": due, "checks": [],
                                  "alerts": [], "state": store["state"]}
                        checks, alerts = run_check_cycle(subset)
                        store["checks"].extend(checks)
                        store["alerts"].extend(alerts)
                        store["state"].update(subset["state"])
                        save_store(args.store, store)
                        for c in checks:
                            print(f"{c['url']}: "
                                  f"{'UP' if c['ok'] else 'DOWN'} "
                                  f"(status {c['status']}, {c['latency_ms']} ms)",
                                  flush=True)
                        for a in alerts:
                            print(f"ALERT [{a['kind']}] {a['url']}: "
                                  f"{a['message']}", flush=True)
                        for t in due:
                            last_check[t["url"]] = time.monotonic()
                    cycles += 1
                    if args.cycles and cycles >= args.cycles:
                        break
                    if (args.max_seconds
                            and time.monotonic() - started >= args.max_seconds):
                        break
                    time.sleep(1)
            except KeyboardInterrupt:
                print(f"\nStopped after {cycles} cycles, "
                      f"{len(store['checks'])} checks recorded.")
        elif args.command == "report":
            from_t = parse_time(args.from_time) if args.from_time else None
            to_t = parse_time(args.to_time) if args.to_time else None
            print(report_text(filter_checks(store, args.url, from_t, to_t)),
                  end="")
        elif args.command == "export":
            checks = filter_checks(store, args.url)
            if args.format == "json":
                with open(args.out, "w", encoding="utf-8") as fh:
                    json.dump(checks, fh, indent=2)
            else:
                fields = ["url", "timestamp", "status", "ok", "latency_ms",
                          "ttfb_ms", "total_ms", "method", "error"]
                with open(args.out, "w", encoding="utf-8", newline="") as fh:
                    writer = csv.DictWriter(fh, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(checks)
            print(f"Exported {len(checks)} checks to {args.out}")
        elif args.command == "alerts":
            events = [a for a in store["alerts"]
                      if not args.url or a["url"] == args.url]
            if not events:
                print("No alerts recorded.")
            for a in events:
                print(f"{a['timestamp']} [{a['kind']}] {a['url']}: "
                      f"{a['message']}")
    except MonitorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
