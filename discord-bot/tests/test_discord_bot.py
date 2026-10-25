"""Tests for discord_bot.py. No network calls to discord.com,
dummyjson.com, or any other host: fetchers are fakes, and the
end-to-end test uses a socketpair with a fake gateway thread.
"""

import io
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import discord_bot as db


def server_frame(payload, opcode=db.WS_TEXT, fin=True):
    """Unmasked server frame (servers never mask)."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    first = (0x80 if fin else 0x00) | opcode
    if len(payload) < 126:
        return bytes([first, len(payload)]) + payload
    if len(payload) < 65536:
        return bytes([first, 126]) + struct.pack("!H", len(payload)) + payload
    return bytes([first, 127]) + struct.pack("!Q", len(payload)) + payload


def fake_quote_fetcher(url):
    assert url == db.QUOTE_URL
    return {"quote": "Test quote.", "author": "Tester"}


def fake_title_fetcher(url):
    return ("<html><head><title>Build Your Own Test | Coding "
            "Challenges</title></head></html>")


def make_dispatcher(catalogue=None, **kw):
    if catalogue is None:
        cat = db.ChallengeCatalogue("/nonexistent.json")
        cat.challenges = []
    else:
        cat = catalogue
    kw.setdefault("quote_fetcher", fake_quote_fetcher)
    kw.setdefault("title_fetcher", fake_title_fetcher)
    return db.Dispatcher(cat, **kw)


def msg(content, username="Alice", bot=False, author_id="111"):
    return {"content": content,
            "author": {"username": username, "bot": bot, "id": author_id},
            "channel_id": "999"}


class TestFraming(unittest.TestCase):
    def roundtrip(self, payload):
        frame = db.ws_encode_frame(payload, mask=b"\x01\x02\x03\x04")
        parsed = db.FrameParser().feed(frame)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0][0], db.WS_TEXT)
        return parsed[0][1]

    def test_small_frame_roundtrip(self):
        self.assertEqual(self.roundtrip("hello"), b"hello")

    def test_16bit_length_roundtrip(self):
        self.assertEqual(self.roundtrip("x" * 200), b"x" * 200)

    def test_64bit_length_roundtrip(self):
        self.assertEqual(self.roundtrip("y" * 70000), b"y" * 70000)

    def test_fragmented_frames_reassemble(self):
        parser = db.FrameParser()
        out = parser.feed(server_frame(b"hel", fin=False))
        self.assertEqual(out, [])
        out = parser.feed(server_frame(b"lo", opcode=db.WS_CONTINUATION,
                                       fin=True))
        self.assertEqual(out, [(db.WS_TEXT, b"hello")])

    def test_ping_and_close_opcodes_reported(self):
        parser = db.FrameParser()
        self.assertEqual(parser.feed(server_frame(b"", opcode=db.WS_PING)),
                         [(db.WS_PING, b"")])
        self.assertEqual(parser.feed(server_frame(b"", opcode=db.WS_CLOSE)),
                         [(db.WS_CLOSE, b"")])

    def test_partial_frame_waits_for_rest(self):
        parser = db.FrameParser()
        frame = server_frame("hello")
        self.assertEqual(parser.feed(frame[:3]), [])
        self.assertEqual(parser.feed(frame[3:]),
                         [(db.WS_TEXT, b"hello")])

    def test_absurd_length_rejected(self):
        bad = bytes([0x81, 127]) + struct.pack("!Q", 10 ** 9)
        with self.assertRaises(ValueError):
            db.FrameParser().feed(bad)

    def test_handshake_request_shape(self):
        req, key = db.ws_handshake_request("gateway.discord.gg", "/?v=10")
        self.assertIn(b"Upgrade: websocket", req)
        self.assertIn(key.encode("ascii"), req)


class TestGatewayPayloads(unittest.TestCase):
    def test_identify_intents(self):
        payload = db.identify_payload("TOKEN")
        self.assertEqual(payload["d"]["intents"], 33281)
        self.assertEqual(payload["d"]["token"], "TOKEN")

    def test_resume_and_heartbeat(self):
        self.assertEqual(db.resume_payload("T", "sess", 42)["d"]["seq"], 42)
        self.assertEqual(db.heartbeat_payload(7)["d"], 7)
        self.assertIsNone(db.heartbeat_payload(None)["d"])

    def test_should_heartbeat(self):
        self.assertTrue(db.should_heartbeat(100.0, None, 41250))
        self.assertFalse(db.should_heartbeat(100.0, 99.0, 41250))
        self.assertTrue(db.should_heartbeat(200.0, 99.0, 41250))

    def test_backoff_capped(self):
        self.assertEqual([db.backoff_seconds(i) for i in range(7)],
                         [1, 2, 4, 8, 16, 30, 30])


class TestGatewayHandling(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.dispatcher = make_dispatcher()
        self.client = db.GatewayClient("TOKEN", self.dispatcher,
                                       lambda ch, c: self.sent.append((ch, c)))

        class FakeSock:
            def __init__(self, outer):
                self.outer = outer

            def sendall(self, data):
                self.outer.raw_sent.append(data)

        self.client.raw_sent = []
        self.client.sock = FakeSock(self.client)

    def test_hello_starts_heartbeat_and_identifies(self):
        self.client.handle_payload(
            {"op": db.OP_HELLO, "d": {"heartbeat_interval": 41250}})
        self.assertEqual(self.client.heartbeat_interval_ms, 41250)
        self.assertTrue(self.client.identified)
        parser = db.FrameParser()
        decoded = []
        for chunk in self.client.raw_sent:
            decoded.extend(parser.feed(chunk))
        ops = [json.loads(p)["op"] for _, p in decoded]
        self.assertIn(db.OP_HEARTBEAT, ops)
        self.assertIn(db.OP_IDENTIFY, ops)

    def test_heartbeat_ack_clears_pending(self):
        self.client.ack_pending = True
        self.client.handle_payload({"op": db.OP_HEARTBEAT_ACK})
        self.assertFalse(self.client.ack_pending)

    def test_op1_requests_heartbeat(self):
        self.client.heartbeat_interval_ms = 41250
        self.client.handle_payload({"op": db.OP_HEARTBEAT})
        self.assertTrue(self.client.ack_pending)

    def test_reconnect_and_invalid_session(self):
        self.assertFalse(
            self.client.handle_payload({"op": db.OP_RECONNECT}))
        self.assertTrue(self.client.reconnect_requested)
        self.client.session_id = "sess"
        self.client.seq = 5
        self.client.handle_payload({"op": db.OP_INVALID_SESSION, "d": False})
        self.assertIsNone(self.client.session_id)
        self.assertIsNone(self.client.seq)

    def test_dispatch_sets_sequence_and_ready(self):
        self.client.handle_payload(
            {"op": db.OP_DISPATCH, "t": "READY", "s": 3,
             "d": {"session_id": "sess", "user": {"id": "BOTID"}}})
        self.assertEqual(self.client.seq, 3)
        self.assertEqual(self.client.session_id, "sess")
        self.assertEqual(self.dispatcher.bot_id, "BOTID")


class TestDispatcher(unittest.TestCase):
    def test_hello_greeting(self):
        d = make_dispatcher()
        self.assertEqual(d.handle_message(msg("Hello")), "Hello, Alice!")
        self.assertEqual(d.handle_message(msg("  HELLO  ")), "Hello, Alice!")
        self.assertIsNone(d.handle_message(msg("Hello there")))
        self.assertIsNone(d.handle_message(msg("hello?")))

    def test_bot_and_self_messages_ignored(self):
        d = make_dispatcher(bot_id="BOTID")
        self.assertIsNone(d.handle_message(msg("Hello", bot=True)))
        self.assertIsNone(d.handle_message(msg("Hello", author_id="BOTID")))
        self.assertIsNone(d.handle_message({"content": None, "author": {}}))

    def test_quote_and_failure(self):
        d = make_dispatcher()
        self.assertEqual(d.handle_message(msg("!quote")),
                         '"Test quote." — Tester')
        d2 = make_dispatcher(quote_fetcher=lambda url: (_ for _ in ()).throw(
            RuntimeError("down")))
        self.assertIn("couldn't fetch", d2.handle_message(msg("!quote")))

    def test_challenge_and_list(self):
        cat = db.ChallengeCatalogue("/nonexistent.json")
        cat.challenges = [{"title": "A", "url": "https://example/a"},
                          {"title": "B", "url": "https://example/b"}]
        d = make_dispatcher(catalogue=cat, rng=random_first)
        self.assertEqual(d.handle_message(msg("!challenge")), "A — https://example/a")
        self.assertEqual(d.handle_message(msg("!list")),
                         "Challenges:\n1. A — https://example/a\n"
                         "2. B — https://example/b")
        cat.challenges = []
        self.assertEqual(d.handle_message(msg("!challenge")),
                         "No challenges in the catalogue yet.")
        self.assertEqual(d.handle_message(msg("!list")), "No challenges yet.")

    def test_add_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cat = db.ChallengeCatalogue(os.path.join(tmp, "c.json"))
            cat.load()
            d = make_dispatcher(catalogue=cat)
            self.assertEqual(d.handle_message(msg("!add")),
                             "Usage: !add <challenge URL>")
            for bad in (
                    "https://example.com/challenges/challenge-x/",
                    "https://codingchallenges.fyi.evil.com/challenges/challenge-x/",
                    "https://evilcodingchallenges.fyi/challenges/challenge-x/",
                    "https://codingchallenges.fyi/other-page/",
                    "not a url"):
                self.assertIn("valid", d.handle_message(msg("!add " + bad)))
            ok = d.handle_message(msg(
                "!add https://codingchallenges.fyi/challenges/challenge-test/"))
            self.assertTrue(ok.startswith("Added: Build Your Own Test"))
            self.assertIn("already listed", d.handle_message(msg(
                "!add https://codingchallenges.fyi/challenges/challenge-test/")))
            # Persistence: reload from disk and the entry is still there.
            cat2 = db.ChallengeCatalogue(os.path.join(tmp, "c.json"))
            cat2.load()
            self.assertEqual(len(cat2.challenges), 1)
            self.assertEqual(cat2.challenges[0]["title"],
                             "Build Your Own Test")

    def test_unknown_command_silent_and_help(self):
        d = make_dispatcher()
        self.assertIsNone(d.handle_message(msg("!bogus")))
        self.assertIn("!quote", d.handle_message(msg("!help")))

    def test_extract_title(self):
        self.assertEqual(
            db.extract_title("<title>Build X | Coding Challenges</title>"),
            "Build X")
        self.assertEqual(
            db.extract_title("<title>Fish &amp; Chips</title>"),
            "Fish & Chips")
        with self.assertRaises(ValueError):
            db.extract_title("<html>no title</html>")


class random_first:
    """Deterministic rng stand-in: choice() always takes the first item."""

    @staticmethod
    def choice(seq):
        return seq[0]


class TestCatalogueLoading(unittest.TestCase):
    def test_missing_and_corrupt_load_empty(self):
        cat = db.ChallengeCatalogue("/nonexistent-xyz.json")
        self.assertEqual(cat.load(), [])
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as f:
            f.write("{not json")
            name = f.name
        try:
            self.assertEqual(db.ChallengeCatalogue(name).load(), [])
        finally:
            os.unlink(name)

    def test_valid_challenge_url(self):
        self.assertTrue(db.is_valid_challenge_url(
            "https://codingchallenges.fyi/challenges/challenge-discord/"))
        self.assertTrue(db.is_valid_challenge_url(
            "http://www.codingchallenges.fyi/challenges/challenge-wc"))
        self.assertFalse(db.is_valid_challenge_url(
            "https://codingchallenges.fyi.evil/challenges/challenge-x"))


class FakeResp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


class TestRest(unittest.TestCase):
    def test_build_send_request(self):
        req = db.build_send_request("123", "hi", "TOKEN")
        self.assertEqual(
            req.full_url,
            "https://discord.com/api/v10/channels/123/messages")
        self.assertEqual(req.get_header("Authorization"), "Bot TOKEN")
        self.assertEqual(json.loads(req.data), {"content": "hi"})
        with self.assertRaises(ValueError):
            db.build_send_request("123", "x" * 2001, "TOKEN")

    def test_send_message_uses_fake_urlopen(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["req"] = req
            return FakeResp({"id": "555"})

        result = db.send_message("123", "hi", "TOKEN", urlopen=fake_urlopen)
        self.assertEqual(result, {"id": "555"})
        self.assertEqual(captured["req"].get_header("Authorization"),
                         "Bot TOKEN")


class TestSocketpairEndToEnd(unittest.TestCase):
    """Client <-> fake gateway over a real socketpair on no TCP port."""

    def test_hello_identify_message_create_and_reconnect(self):
        client_end, server_end = socket.socketpair()
        client_end.settimeout(5)
        server_end.settimeout(5)
        sent = []

        dispatcher = make_dispatcher()
        client = db.GatewayClient("TOKEN", dispatcher,
                                  lambda ch, c: sent.append((ch, c)))
        client.sock = client_end

        errors = []

        def fake_gateway():
            try:
                server_end.sendall(server_frame(json.dumps(
                    {"op": db.OP_HELLO, "d": {"heartbeat_interval": 41250}})))
                # Read frames until Identify arrives.
                parser = db.FrameParser()
                buf = b""
                while True:
                    chunk = server_end.recv(65536)
                    if not chunk:
                        return
                    for _op, payload in parser.feed(chunk):
                        if json.loads(payload)["op"] == db.OP_IDENTIFY:
                            break
                    else:
                        continue
                    break
                server_end.sendall(server_frame(json.dumps(
                    {"op": db.OP_DISPATCH, "t": "MESSAGE_CREATE", "s": 1,
                     "d": msg("Hello", username="Bob")})))
                # Give the client a moment, then ask it to reconnect.
                import time as _time
                _time.sleep(0.5)
                server_end.sendall(server_frame(json.dumps(
                    {"op": db.OP_RECONNECT})))
            except Exception as exc:  # surfaced to the test below
                errors.append(exc)

        thread = threading.Thread(target=fake_gateway, daemon=True)
        thread.start()
        try:
            steps = 0
            while client.step() and steps < 50:
                steps += 1
        finally:
            client_end.close()
            server_end.close()
        thread.join(timeout=5)
        self.assertEqual(errors, [])
        self.assertEqual(sent, [("999", "Hello, Bob!")])
        self.assertTrue(client.reconnect_requested)


class TestCli(unittest.TestCase):
    def test_missing_token_exits_2(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                self.assertEqual(db.main([]), 2)
            self.assertIn("DISCORD_BOT_TOKEN", err.getvalue())


if __name__ == "__main__":
    unittest.main()
