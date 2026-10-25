"""Tests for rate_limiter.py — all driven by FakeClock, no sleeps."""

import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rate_limiter import (  # noqa: E402
    FakeClock,
    FixedWindowLimiter,
    InMemorySharedStore,
    SharedSlidingWindowCounterLimiter,
    SlidingWindowCounterLimiter,
    SlidingWindowLogLimiter,
    TokenBucketLimiter,
    make_server,
)


class TestTokenBucket(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.limiter = TokenBucketLimiter(10, 1, now=self.clock.now)

    def test_starts_full_then_rejects(self):
        self.assertEqual([self.limiter.allow("ip") for _ in range(10)],
                         [True] * 10)
        self.assertFalse(self.limiter.allow("ip"))

    def test_rejection_consumes_nothing(self):
        for _ in range(10):
            self.limiter.allow("ip")
        self.assertFalse(self.limiter.allow("ip"))
        self.assertFalse(self.limiter.allow("ip"))
        self.clock.advance(1)
        self.assertTrue(self.limiter.allow("ip"))
        self.assertFalse(self.limiter.allow("ip"))

    def test_refill_caps_at_capacity(self):
        for _ in range(10):
            self.limiter.allow("ip")
        self.clock.advance(100)  # would be 100 tokens, capped at 10
        self.assertEqual([self.limiter.allow("ip") for _ in range(10)],
                         [True] * 10)
        self.assertFalse(self.limiter.allow("ip"))

    def test_fractional_refill_is_not_a_token(self):
        for _ in range(10):
            self.limiter.allow("ip")
        self.clock.advance(0.5)
        self.assertFalse(self.limiter.allow("ip"))
        self.clock.advance(0.5)
        self.assertTrue(self.limiter.allow("ip"))

    def test_keys_are_independent(self):
        for _ in range(10):
            self.limiter.allow("a")
        self.assertFalse(self.limiter.allow("a"))
        self.assertTrue(self.limiter.allow("b"))

    def test_cost_validation_and_oversized_cost(self):
        with self.assertRaises(ValueError):
            self.limiter.allow("ip", cost=0)
        with self.assertRaises(ValueError):
            self.limiter.allow("ip", cost=-1)
        self.assertFalse(self.limiter.allow("ip", cost=11))

    def test_remaining(self):
        self.assertEqual(self.limiter.remaining("ip"), 10)
        self.limiter.allow("ip")
        self.assertEqual(self.limiter.remaining("ip"), 9)


class TestFixedWindow(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.limiter = FixedWindowLimiter(10, 3, now=self.clock.now)

    def test_limit_then_reject_within_window(self):
        self.assertEqual([self.limiter.allow("ip") for _ in range(3)],
                         [True] * 3)
        self.assertFalse(self.limiter.allow("ip"))

    def test_boundary_burst_after_rollover(self):
        for _ in range(3):
            self.limiter.allow("ip")
        self.clock.advance(9)
        self.assertFalse(self.limiter.allow("ip"))  # still window 0-10
        self.clock.advance(1)  # t=10, new window
        self.assertEqual([self.limiter.allow("ip") for _ in range(3)],
                         [True] * 3)
        self.assertFalse(self.limiter.allow("ip"))

    def test_keys_are_independent(self):
        for _ in range(3):
            self.limiter.allow("a")
        self.assertTrue(self.limiter.allow("b"))


class TestSlidingWindowLog(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.limiter = SlidingWindowLogLimiter(10, 3, now=self.clock.now)

    def test_limit_then_expire(self):
        self.clock.advance(0)
        self.assertTrue(self.limiter.allow("ip"))   # t=0
        self.clock.advance(1)
        self.assertTrue(self.limiter.allow("ip"))   # t=1
        self.clock.advance(1)
        self.assertTrue(self.limiter.allow("ip"))   # t=2
        self.clock.advance(1)
        self.assertFalse(self.limiter.allow("ip"))  # t=3, rejected, not logged
        self.clock.advance(7)  # t=10: entry at t=0 pruned, one slot free
        self.assertTrue(self.limiter.allow("ip"))
        self.assertFalse(self.limiter.allow("ip"))
        self.clock.advance(1)  # t=11: entry at t=1 pruned
        self.assertTrue(self.limiter.allow("ip"))

    def test_fractional_cost_rejected(self):
        with self.assertRaises(ValueError):
            self.limiter.allow("ip", cost=1.5)


class TestSlidingWindowCounter(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.limiter = SlidingWindowCounterLimiter(10, 10, now=self.clock.now)

    def test_fresh_window_limit(self):
        self.assertEqual([self.limiter.allow("ip") for _ in range(10)],
                         [True] * 10)
        self.assertFalse(self.limiter.allow("ip"))

    def test_weighted_smoothing_page_example(self):
        # Fill the previous window completely (t=0..9).
        for i in range(10):
            self.clock.advance(1) if i else None
            self.assertTrue(self.limiter.allow("ip"))
        # 40% through the new window: previous counts at 60% -> 6.
        self.clock.advance(5)  # t=14
        self.assertAlmostEqual(self.limiter.weighted_count("ip"), 6.0)
        self.assertEqual([self.limiter.allow("ip") for _ in range(4)],
                         [True] * 4)
        self.assertFalse(self.limiter.allow("ip"))

    def test_old_window_stops_counting(self):
        for _ in range(10):
            self.limiter.allow("ip")
        self.clock.advance(34)  # window 30-40, previous window empty
        self.assertEqual([self.limiter.allow("ip") for _ in range(10)],
                         [True] * 10)

    def test_keys_are_independent(self):
        for _ in range(10):
            self.limiter.allow("a")
        self.assertTrue(self.limiter.allow("b"))


class TestSharedCounter(unittest.TestCase):
    def test_two_instances_share_one_allowance(self):
        clock = FakeClock()
        store = InMemorySharedStore()
        a = SharedSlidingWindowCounterLimiter(60, 3, store, now=clock.now)
        b = SharedSlidingWindowCounterLimiter(60, 3, store, now=clock.now)
        self.assertTrue(a.allow("ip"))
        self.assertTrue(a.allow("ip"))
        self.assertTrue(b.allow("ip"))
        self.assertFalse(b.allow("ip"))
        self.assertFalse(a.allow("ip"))

    def test_separate_stores_do_not_share(self):
        clock = FakeClock()
        a = SharedSlidingWindowCounterLimiter(
            60, 2, InMemorySharedStore(), now=clock.now)
        b = SharedSlidingWindowCounterLimiter(
            60, 2, InMemorySharedStore(), now=clock.now)
        self.assertTrue(a.allow("ip"))
        self.assertTrue(a.allow("ip"))
        self.assertTrue(b.allow("ip"))


class TestServer(unittest.TestCase):
    def setUp(self):
        clock = FakeClock()
        limiter = TokenBucketLimiter(2, 0, now=clock.now)  # refill 0: deterministic
        self.server = make_server(limiter, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _get(self, path):
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d%s" % (self.port, path)) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_unlimited_always_200(self):
        for _ in range(3):
            self.assertEqual(self._get("/unlimited"),
                             (200, "Unlimited! Let's Go!"))

    def test_limited_then_429(self):
        self.assertEqual(self._get("/limited"),
                         (200, "Limited, don't over use me!"))
        self.assertEqual(self._get("/limited"),
                         (200, "Limited, don't over use me!"))
        status, _ = self._get("/limited")
        self.assertEqual(status, 429)

    def test_unknown_path_404(self):
        status, _ = self._get("/nope")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
