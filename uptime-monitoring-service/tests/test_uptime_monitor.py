"""Tests for uptime_monitor.py. Local fake servers on ephemeral ports only."""

import http.server
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uptime_monitor as um


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class FakeHandler(http.server.BaseHTTPRequestHandler):
    status = 200
    body = b"hello"
    delay = 0.0

    def _handle(self):
        if self.delay:
            time.sleep(self.delay)
        self.send_response(type(self).status)
        self.send_header("Content-Length", str(len(type(self).body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(type(self).body)

    do_GET = _handle
    do_HEAD = _handle

    def log_message(self, *args):  # keep test output clean
        pass


class WebhookHandler(http.server.BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        type(self).received.append(json.loads(self.rfile.read(length)))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def start_server(handler_cls):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


class MonitorTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store_path = os.path.join(self.tmp.name, "store.json")
        self.servers = []
        FakeHandler.status = 200
        FakeHandler.body = b"hello"
        FakeHandler.delay = 0.0
        WebhookHandler.received = []

    def tearDown(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()
        self.tmp.cleanup()

    def serve(self, handler=FakeHandler):
        server, port = start_server(handler)
        self.servers.append(server)
        return f"http://127.0.0.1:{port}/health"

    def store(self):
        return um.load_store(self.store_path)

    def save(self, store):
        um.save_store(self.store_path, store)

    def add(self, url, **kw):
        store = self.store()
        target = um.add_target(store, url, **kw)
        self.save(store)
        return target

    def check_once(self, target):
        store = self.store()
        check = um.perform_check(target)
        store["checks"].append(check)
        um.evaluate_alerts(store, target, check)
        self.save(store)
        return check

    # -- validation / CRUD

    def test_add_accepts_http_and_https_urls(self):
        store = um.empty_store()
        um.add_target(store, "http://example.local/x")
        um.add_target(store, "https://example.local/y")
        self.assertEqual(len(store["targets"]), 2)

    def test_add_rejects_bad_url(self):
        store = um.empty_store()
        for bad in ["not-a-url", "ftp://example.local", "http://", ""]:
            with self.subTest(bad=bad):
                with self.assertRaises(um.MonitorError):
                    um.add_target(store, bad)

    def test_add_rejects_interval_below_one(self):
        store = um.empty_store()
        with self.assertRaises(um.MonitorError):
            um.add_target(store, "http://127.0.0.1/x", interval=0)

    def test_add_accepts_interval_one(self):
        store = um.empty_store()
        um.add_target(store, "http://127.0.0.1/x", interval=1)
        self.assertEqual(store["targets"][0]["interval_seconds"], 1)

    def test_add_rejects_bad_method(self):
        store = um.empty_store()
        with self.assertRaises(um.MonitorError):
            um.add_target(store, "http://127.0.0.1/x", method="POST")

    def test_add_duplicate_rejected(self):
        store = um.empty_store()
        um.add_target(store, "http://127.0.0.1/x")
        with self.assertRaises(um.MonitorError):
            um.add_target(store, "http://127.0.0.1/x")

    def test_remove_and_remove_unknown(self):
        store = um.empty_store()
        um.add_target(store, "http://127.0.0.1/x")
        um.remove_target(store, "http://127.0.0.1/x")
        self.assertEqual(store["targets"], [])
        with self.assertRaises(um.MonitorError):
            um.remove_target(store, "http://127.0.0.1/x")

    # -- checks

    def test_head_check_records_success(self):
        url = self.serve()
        target = self.add(url, method="HEAD")
        check = self.check_once(target)
        self.assertTrue(check["ok"])
        self.assertEqual(check["status"], 200)
        self.assertIsNotNone(check["latency_ms"])
        self.assertGreaterEqual(check["latency_ms"], 0)

    def test_head_check_records_server_error_as_down(self):
        FakeHandler.status = 500
        url = self.serve()
        target = self.add(url, method="HEAD")
        check = self.check_once(target)
        self.assertFalse(check["ok"])
        self.assertEqual(check["status"], 500)

    def test_check_unreachable_target_records_error(self):
        target = self.add(f"http://127.0.0.1:{free_port()}/", method="HEAD")
        check = self.check_once(target)
        self.assertFalse(check["ok"])
        self.assertIsNone(check["status"])
        self.assertIsNotNone(check["error"])

    def test_get_check_records_ttfb_and_total(self):
        url = self.serve()
        target = self.add(url, method="GET")
        check = self.check_once(target)
        self.assertTrue(check["ok"])
        self.assertIsNotNone(check["ttfb_ms"])
        self.assertIsNotNone(check["total_ms"])
        self.assertLessEqual(check["ttfb_ms"], check["total_ms"])

    def test_get_check_slow_body_ttfb_less_than_total(self):
        # Delayed body: override handler to sleep between headers and body.
        class SlowBodyHandler(FakeHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", "5")
                self.end_headers()
                self.wfile.write(b"a")
                time.sleep(0.2)
                self.wfile.write(b"bcde")

            def log_message(self, *args):
                pass

        server, port = start_server(SlowBodyHandler)
        self.servers.append(server)
        target = self.add(f"http://127.0.0.1:{port}/", method="GET")
        check = self.check_once(target)
        self.assertTrue(check["ok"])
        self.assertLess(check["ttfb_ms"], check["total_ms"])
        self.assertGreaterEqual(check["total_ms"], 150)

    def test_one_bad_target_does_not_block_others(self):
        good = self.serve()
        bad_url = f"http://127.0.0.1:{free_port()}/"
        store = self.store()
        um.add_target(store, bad_url)
        um.add_target(store, good)
        self.save(store)
        checks, _ = um.run_check_cycle(store)
        self.assertEqual(len(checks), 2)
        by_url = {c["url"]: c for c in checks}
        self.assertFalse(by_url[bad_url]["ok"])
        self.assertTrue(by_url[good]["ok"])

    # -- alerts

    def test_no_alert_below_threshold(self):
        target = self.add(f"http://127.0.0.1:{free_port()}/",
                          alert_after=3)
        self.check_once(target)
        self.check_once(target)
        self.assertEqual(self.store()["alerts"], [])

    def test_down_alert_after_n_failures_once_per_incident(self):
        target = self.add(f"http://127.0.0.1:{free_port()}/",
                          alert_after=2)
        self.check_once(target)
        self.check_once(target)
        self.check_once(target)  # still same incident: no repeat
        alerts = self.store()["alerts"]
        downs = [a for a in alerts if a["kind"] == "DOWN"]
        self.assertEqual(len(downs), 1)
        self.assertEqual(downs[0]["consecutive_failures"], 2)

    def test_recovery_alert_after_incident(self):
        url = self.serve()
        target = self.add(url, alert_after=1)
        FakeHandler.status = 500
        self.check_once(target)
        self.assertTrue(any(a["kind"] == "DOWN"
                            for a in self.store()["alerts"]))
        FakeHandler.status = 200
        self.check_once(target)  # good server again
        kinds = [a["kind"] for a in self.store()["alerts"]]
        self.assertIn("RECOVERY", kinds)

    def test_slow_alert_and_no_failure_count(self):
        FakeHandler.delay = 0.05
        url = self.serve()
        target = self.add(url, method="HEAD", slow_threshold_ms=1)
        check = self.check_once(target)
        self.assertTrue(check["ok"])
        store = self.store()
        self.assertTrue(any(a["kind"] == "SLOW" for a in store["alerts"]))
        self.assertEqual(
            store["state"][url]["consecutive_failures"], 0)

    def test_alert_log_sink(self):
        log_path = os.path.join(self.tmp.name, "alerts.log")
        target = self.add(f"http://127.0.0.1:{free_port()}/",
                          alert_after=1, alert_log=log_path)
        self.check_once(target)
        with open(log_path, encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("[DOWN]", content)

    def test_email_hook_sink(self):
        hook_path = os.path.join(self.tmp.name, "outbox.txt")
        target = self.add(f"http://127.0.0.1:{free_port()}/",
                          alert_after=1, email_hook=hook_path)
        self.check_once(target)
        with open(hook_path, encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("Subject: Uptime alert [DOWN]", content)

    def test_webhook_sink_posts_json(self):
        hook_url = self.serve(WebhookHandler)
        target = self.add(f"http://127.0.0.1:{free_port()}/",
                          alert_after=1, webhook=hook_url)
        self.check_once(target)
        self.assertEqual(len(WebhookHandler.received), 1)
        self.assertEqual(WebhookHandler.received[0]["kind"], "DOWN")

    # -- reports / export / run / persistence

    def _seed_checks(self, url, oks):
        store = self.store()
        for i, ok in enumerate(oks):
            store["checks"].append({
                "url": url, "timestamp": f"2026-10-25T10:0{i}:00+00:00",
                "status": 200 if ok else 500, "ok": ok,
                "latency_ms": 10.0 + i, "ttfb_ms": None,
                "total_ms": 10.0 + i, "method": "HEAD", "error": None})
        self.save(store)

    def test_report_uptime_math(self):
        url = "http://127.0.0.1:9/x"
        self._seed_checks(url, [True, True, False, True])
        text = um.report_text(um.filter_checks(self.store(), url))
        self.assertIn("Uptime: 75.0%", text)
        self.assertIn("Checks: 4", text)

    def test_report_date_range_filter(self):
        url = "http://127.0.0.1:9/x"
        self._seed_checks(url, [True, True, True])
        checks = um.filter_checks(
            self.store(), url,
            from_time=um.parse_time("2026-10-25T10:01:00+00:00"),
            to_time=um.parse_time("2026-10-25T10:01:59+00:00"))
        self.assertEqual(len(checks), 1)

    def test_report_empty_range_is_na(self):
        text = um.report_text([])
        self.assertIn("Uptime: n/a", text)

    def test_report_contains_sparkline(self):
        url = "http://127.0.0.1:9/x"
        self._seed_checks(url, [True, True])
        text = um.report_text(um.filter_checks(self.store(), url))
        self.assertIn("Latency graph:", text)
        self.assertTrue(any(ch in text for ch in "▁▂▃▄▅▆▇█"))

    def test_export_json_and_csv(self):
        url = "http://127.0.0.1:9/x"
        self._seed_checks(url, [True, False])
        checks = um.filter_checks(self.store(), url)
        json_path = os.path.join(self.tmp.name, "out.json")
        csv_path = os.path.join(self.tmp.name, "out.csv")
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh)
        with open(json_path, encoding="utf-8") as fh:
            self.assertEqual(len(json.load(fh)), 2)
        import csv as csv_mod
        fields = ["url", "timestamp", "status", "ok", "latency_ms",
                  "ttfb_ms", "total_ms", "method", "error"]
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv_mod.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(checks)
        with open(csv_path, encoding="utf-8") as fh:
            rows = list(csv_mod.DictReader(fh))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "200")

    def test_run_cycles_checks_due_targets(self):
        url = self.serve()
        self.add(url, interval=1)
        rc = um.main(["--store", self.store_path, "run", "--cycles", "2"])
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(len(self.store()["checks"]), 1)

    def test_cli_check_single_url_no_duplicate(self):
        url = self.serve()
        other = self.serve()
        self.add(url, interval=60)
        self.add(other, interval=60)
        rc = um.main(["--store", self.store_path, "check", "--url", url])
        self.assertEqual(rc, 0)
        checks = [c for c in self.store()["checks"] if c["url"] == url]
        self.assertEqual(len(checks), 1)

    def test_store_persists_across_loads(self):
        url = self.serve()
        target = self.add(url)
        self.check_once(target)
        reloaded = um.load_store(self.store_path)
        self.assertEqual(len(reloaded["checks"]), 1)
        self.assertEqual(reloaded["targets"][0]["url"], url)

    def test_corrupt_store_raises(self):
        with open(self.store_path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        with self.assertRaises(um.MonitorError):
            um.load_store(self.store_path)


if __name__ == "__main__":
    unittest.main()
