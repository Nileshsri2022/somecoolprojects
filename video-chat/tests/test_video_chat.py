"""Tests for video_chat.py: real server on an ephemeral port,
talked to over HTTP via the Client class. No server mocks."""

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from video_chat import Client, ClientError, make_server  # noqa: E402


def raw(base, method, path, body=None, raw_body=None):
    data = raw_body if raw_body is not None else (
        json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


class ServerCase(unittest.TestCase):
    def setUp(self):
        self.server = make_server("127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        port = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % port
        self.alice = Client(self.base)
        self.bob = Client(self.base)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    # health and rooms

    def test_health_and_empty_rooms(self):
        health = self.alice.health()
        self.assertEqual(health["service"], "video-chat-signalling")
        self.assertEqual(health["rooms"], 0)
        self.assertEqual(self.alice.list_rooms(), [])

    def test_room_appears_and_disappears(self):
        self.alice.join("room-a", "alice")
        self.assertEqual(self.alice.list_rooms(), ["room-a"])
        self.alice.leave("room-a", "alice")
        self.assertEqual(self.alice.list_rooms(), [])

    # join / leave

    def test_join_peer_list_and_peer_joined(self):
        self.assertEqual(self.alice.join("room-a", "alice")["peers"], [])
        self.assertEqual(self.bob.join("room-a", "bob")["peers"], ["alice"])
        joined = [m for m in self.alice.poll("room-a", "alice")
                  if m["type"] == "peer-joined"]
        self.assertEqual([m["payload"] for m in joined], [{"user": "bob"}])

    def test_rejoin_is_idempotent(self):
        self.alice.join("room-a", "alice")
        self.bob.join("room-a", "bob")
        self.alice.poll("room-a", "alice")  # drain peer-joined
        again = self.alice.join("room-a", "alice")
        self.assertEqual(again["peers"], ["bob"])
        joined = [m for m in self.bob.poll("room-a", "bob")
                  if m["type"] == "peer-joined"]
        self.assertEqual(joined, [])

    def test_leave_broadcasts_peer_left(self):
        self.alice.join("room-a", "alice")
        self.bob.join("room-a", "bob")
        self.alice.leave("room-a", "alice")
        left = [m for m in self.bob.poll("room-a", "bob")
                if m["type"] == "peer-left"]
        self.assertEqual([m["payload"] for m in left], [{"user": "alice"}])

    def test_leave_nonmember_and_unknown_room(self):
        self.alice.join("room-a", "alice")
        with self.assertRaises(ClientError):
            self.bob.leave("room-a", "bob")
        with self.assertRaises(ClientError):
            self.alice.leave("no-such-room", "alice")
        self.assertEqual(self.alice.list_rooms(), ["room-a"])

    # send / poll: the full signalling flow

    def test_full_call_flow_in_order(self):
        self.alice.join("room-a", "alice")
        self.bob.join("room-a", "bob")
        offer = {"sdp": "v=0\r\no=alice 1 1 IN IP4 127.0.0.1\r\n",
                 "type": "offer"}
        self.alice.send("room-a", "alice", "offer", offer, to="bob")
        got = [m for m in self.bob.poll("room-a", "bob")
               if m["type"] == "offer"]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["payload"], offer)
        self.assertEqual(got[0]["from"], "alice")
        answer = {"sdp": "v=0\r\no=bob 1 1 IN IP4 127.0.0.1\r\n",
                  "type": "answer"}
        self.bob.send("room-a", "bob", "answer", answer, to="alice")
        got = [m for m in self.alice.poll("room-a", "alice")
               if m["type"] == "answer"]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["payload"], answer)
        self.alice.send("room-a", "alice", "candidate",
                        {"candidate": "candidate:1 1 udp 1 127.0.0.1 5000"},
                        to="bob")
        self.bob.send("room-a", "bob", "candidate",
                      {"candidate": "candidate:1 1 udp 1 127.0.0.1 5001"},
                      to="alice")
        self.assertTrue(any(m["type"] == "candidate"
                            for m in self.bob.poll("room-a", "bob")))
        self.assertTrue(any(m["type"] == "candidate"
                            for m in self.alice.poll("room-a", "alice")))
        self.alice.send("room-a", "alice", "chat", "hi bob", to="bob")
        self.bob.send("room-a", "bob", "chat", "hi alice", to="alice")
        self.assertTrue(any(m["type"] == "chat"
                            and m["payload"] == "hi bob"
                            for m in self.bob.poll("room-a", "bob")))
        self.assertTrue(any(m["type"] == "chat"
                            and m["payload"] == "hi alice"
                            for m in self.alice.poll("room-a", "alice")))
        self.alice.send("room-a", "alice", "bye", None, to="bob")
        self.assertTrue(any(m["type"] == "bye"
                            for m in self.bob.poll("room-a", "bob")))
        # Sequence numbers strictly increase in poll order.
        seqs = [m["seq"] for m in self.bob.poll("room-a", "bob", since=0)]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), len(set(seqs)))

    def test_broadcast_not_echoed_to_sender(self):
        self.alice.join("room-a", "alice")
        self.bob.join("room-a", "bob")
        carol = Client(self.base)
        carol.join("room-a", "carol")
        self.alice.send("room-a", "alice", "chat", "hello all")
        self.assertTrue(any(m["type"] == "chat"
                            and m["payload"] == "hello all"
                            for m in self.bob.poll("room-a", "bob")))
        self.assertTrue(any(m["type"] == "chat"
                            and m["payload"] == "hello all"
                            for m in carol.poll("room-a", "carol")))
        self.assertFalse(any(m["type"] == "chat"
                             for m in self.alice.poll("room-a", "alice")))

    def test_poll_since_cursor_is_idempotent(self):
        self.alice.join("room-a", "alice")
        self.bob.join("room-a", "bob")
        self.alice.send("room-a", "alice", "chat", "one", to="bob")
        first = self.bob.poll("room-a", "bob", since=0)
        again = self.bob.poll("room-a", "bob", since=0)
        self.assertEqual(first, again)
        last_seq = first[-1]["seq"]
        self.assertEqual(self.bob.poll("room-a", "bob", since=last_seq), [])

    def test_rooms_are_isolated(self):
        self.alice.join("room-a", "alice")
        self.bob.join("room-a", "bob")
        self.alice.join("room-b", "alice")
        carol = Client(self.base)
        carol.join("room-b", "carol")
        self.alice.send("room-a", "alice", "chat", "secret-a", to="bob")
        self.assertFalse(any(m["payload"] == "secret-a"
                             for m in carol.poll("room-b", "carol")))
        self.assertFalse(any(m["payload"] == "secret-a"
                             for m in self.alice.poll("room-b", "alice")))

    def test_payload_relayed_opaquely(self):
        self.alice.join("room-a", "alice")
        self.bob.join("room-a", "bob")
        nested = {"sdp": "v=0", "ice": [{"a": 1}, {"b": [2, 3]}]}
        self.alice.send("room-a", "alice", "offer", nested, to="bob")
        got = [m for m in self.bob.poll("room-a", "bob")
               if m["type"] == "offer"]
        self.assertEqual(got[0]["payload"], nested)

    # validation / errors

    def test_invalid_names_rejected(self):
        for room, user in [("", "alice"), ("room a", "alice"),
                           ("room/a", "alice"), ("room-a", ""),
                           ("room-a", "a b"), ("r" * 65, "alice"),
                           ("room-a", "u" * 65)]:
            status, body = raw(self.base, "POST", "/rooms",
                               {"room": room, "user": user})
            self.assertEqual(status, 400, (room, user, body))
            self.assertIn("error", body)

    def test_malformed_and_non_object_bodies(self):
        status, _ = raw(self.base, "POST", "/rooms",
                        raw_body=b"{not json")
        self.assertEqual(status, 400)
        status, _ = raw(self.base, "POST", "/rooms",
                        raw_body=b"[1, 2]")
        self.assertEqual(status, 400)
        status, _ = raw(self.base, "POST", "/rooms", {"room": "room-a"})
        self.assertEqual(status, 400)

    def test_unknown_message_type_rejected(self):
        self.alice.join("room-a", "alice")
        self.bob.join("room-a", "bob")
        with self.assertRaises(ClientError):
            self.alice.send("room-a", "alice", "video-frame", {}, to="bob")
        self.assertFalse(any(m["type"] == "video-frame"
                             for m in self.bob.poll("room-a", "bob")))

    def test_membership_and_recipient_errors(self):
        self.alice.join("room-a", "alice")
        with self.assertRaises(ClientError):  # bob not a member
            self.bob.send("room-a", "bob", "chat", "hi", to="alice")
        with self.assertRaises(ClientError):  # unknown recipient
            self.alice.send("room-a", "alice", "chat", "hi", to="mallory")
        with self.assertRaises(ClientError):  # poll unknown room
            self.alice.poll("no-such-room", "alice")
        self.bob.join("room-a", "bob")
        with self.assertRaises(ClientError):  # poll as non-member
            Client(self.base).poll("room-a", "mallory")

    def test_unknown_route_is_json_404(self):
        status, body = raw(self.base, "GET", "/nope")
        self.assertEqual(status, 404)
        self.assertIn("error", body)


if __name__ == "__main__":
    unittest.main()
