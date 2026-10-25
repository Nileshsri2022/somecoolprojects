#!/usr/bin/env python3
"""WebRTC-style signalling server + local test-harness client.

Implements Step 1 of the Coding Challenges "Build Your Own
Video Chat Application" challenge
(https://codingchallenges.fyi/challenges/challenge-video-chat/):
a JSON-over-HTTP server that lets two peers find each other in
a named room and relay offer / answer / ICE candidate messages,
plus chat and bye. Payloads are relayed opaquely -- the server
never interprets SDP or ICE data.

This is signalling ONLY. It carries no audio or video: no
WebRTC media, codecs, camera/mic capture, or STUN/TURN. See
README.md. The `demo` command proves the signalling flow end
to end with two scripted peers (the challenge page's Step 3
text fallback).

Python 3 standard library only. Usage:

    python3 video_chat.py serve [--host HOST] [--port PORT]
    python3 video_chat.py demo [--host HOST] [--port PORT]
"""

import argparse
import json
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = 1
MAX_BODY = 64 * 1024
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CLIENT_TYPES = ("offer", "answer", "candidate", "chat", "bye")
SERVER_TYPES = ("peer-joined", "peer-left")


class ApiError(Exception):
    """An error that maps to an HTTP status + JSON body."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def check_name(value, what):
    if not isinstance(value, str) or not NAME_RE.match(value):
        raise ApiError(400, "%s must be 1-64 chars of [A-Za-z0-9_-]" % what)
    return value


class SignallingStore:
    """In-memory rooms, guarded by one lock. All policy lives here."""

    def __init__(self):
        self.lock = threading.Lock()
        self.rooms = {}  # room -> {"members": set, "messages": [msg]}

    def _room(self, room):
        try:
            return self.rooms[room]
        except KeyError:
            raise ApiError(404, "unknown room: %s" % room)

    def _require_member(self, data, room, user):
        if user not in data["members"]:
            raise ApiError(403, "user %s is not a member of %s" % (user, room))

    def _append(self, data, sender, to, msg_type, payload):
        seq = len(data["messages"]) + 1
        msg = {"seq": seq, "from": sender, "to": to,
               "type": msg_type, "payload": payload}
        data["messages"].append(msg)
        return msg

    def list_rooms(self):
        with self.lock:
            return sorted(self.rooms)

    def room_count(self):
        with self.lock:
            return len(self.rooms)

    def join(self, room, user):
        check_name(room, "room")
        check_name(user, "user")
        with self.lock:
            data = self.rooms.setdefault(room, {"members": set(),
                                                "messages": []})
            already = user in data["members"]
            peers = sorted(data["members"] - {user})
            if not already:
                data["members"].add(user)
                for peer in peers:
                    self._append(data, user, peer, "peer-joined",
                                 {"user": user})
            return {"room": room, "user": user, "peers": peers}

    def leave(self, room, user):
        check_name(room, "room")
        check_name(user, "user")
        with self.lock:
            data = self._room(room)
            if user not in data["members"]:
                raise ApiError(404, "user %s is not in %s" % (user, room))
            data["members"].discard(user)
            for peer in sorted(data["members"]):
                self._append(data, user, peer, "peer-left",
                             {"user": user})
            if not data["members"]:
                del self.rooms[room]
            return {"room": room, "user": user, "left": True}

    def send(self, room, sender, to, msg_type, payload):
        check_name(room, "room")
        check_name(sender, "from")
        if msg_type not in CLIENT_TYPES:
            raise ApiError(400, "unknown message type: %r" % (msg_type,))
        if to is not None:
            check_name(to, "to")
        with self.lock:
            data = self._room(room)
            self._require_member(data, room, sender)
            if to is not None and to not in data["members"]:
                raise ApiError(404, "unknown recipient: %s" % to)
            msg = self._append(data, sender, to, msg_type, payload)
            return {"seq": msg["seq"]}

    def poll(self, room, user, since):
        check_name(room, "room")
        check_name(user, "user")
        if not isinstance(since, int) or since < 0:
            raise ApiError(400, "since must be a non-negative integer")
        with self.lock:
            data = self._room(room)
            self._require_member(data, room, user)
            visible = [m for m in data["messages"]
                       if m["seq"] > since
                       and m["from"] != user
                       and (m["to"] is None or m["to"] == user)]
            return {"room": room, "user": user, "since": since,
                    "messages": visible}


def make_handler(store):
    class SignallingHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep test/demo output clean
            pass

        def _json(self, status, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError(400, "request body exceeds 64 KiB")
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw.decode("utf-8")) if raw else None
            except (ValueError, UnicodeDecodeError):
                raise ApiError(400, "request body is not valid JSON")
            if not isinstance(body, dict):
                raise ApiError(400, "request body must be a JSON object")
            return body

        def _route(self):
            parsed = urllib.parse.urlparse(self.path)
            parts = [p for p in parsed.path.split("/") if p]
            query = urllib.parse.parse_qs(parsed.query)
            method = self.command
            try:
                if method == "GET" and parts == []:
                    self._json(200, {"service": "video-chat-signalling",
                                     "version": VERSION,
                                     "rooms": store.room_count()})
                elif method == "GET" and parts == ["rooms"]:
                    self._json(200, {"rooms": store.list_rooms()})
                elif method == "POST" and parts == ["rooms"]:
                    body = self._read_body()
                    if "room" not in body or "user" not in body:
                        raise ApiError(400, "room and user are required")
                    self._json(200, store.join(body["room"], body["user"]))
                elif len(parts) == 3 and parts[0] == "rooms" \
                        and parts[2] == "leave" and method == "POST":
                    body = self._read_body()
                    if "user" not in body:
                        raise ApiError(400, "user is required")
                    self._json(200, store.leave(parts[1], body["user"]))
                elif len(parts) == 3 and parts[0] == "rooms" \
                        and parts[2] == "messages" and method == "POST":
                    body = self._read_body()
                    for field in ("from", "type"):
                        if field not in body:
                            raise ApiError(400, "%s is required" % field)
                    self._json(200, store.send(
                        parts[1], body["from"], body.get("to"),
                        body["type"], body.get("payload")))
                elif len(parts) == 3 and parts[0] == "rooms" \
                        and parts[2] == "messages" and method == "GET":
                    user = query.get("user", [None])[0]
                    if user is None:
                        raise ApiError(400, "user query param is required")
                    try:
                        since = int(query.get("since", ["0"])[0])
                    except ValueError:
                        raise ApiError(400, "since must be an integer")
                    self._json(200, store.poll(parts[1], user, since))
                else:
                    raise ApiError(404, "unknown route")
            except ApiError as exc:
                self._json(exc.status, {"error": exc.message})

        do_GET = _route
        do_POST = _route

    return SignallingHandler


def make_server(host, port):
    server = ThreadingHTTPServer((host, port),
                                 make_handler(SignallingStore()))
    server.daemon_threads = True
    return server


class ClientError(Exception):
    pass


class Client:
    """Thin HTTP client for the signalling API."""

    def __init__(self, base):
        self.base = base.rstrip("/")

    def _request(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data,
                                     method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
                msg = detail.get("error", exc.reason)
            except ValueError:
                msg = exc.reason
            raise ClientError("%s %s -> %s" % (method, path, msg))

    def health(self):
        return self._request("GET", "/")

    def list_rooms(self):
        return self._request("GET", "/rooms")["rooms"]

    def join(self, room, user):
        return self._request("POST", "/rooms", {"room": room, "user": user})

    def leave(self, room, user):
        return self._request("POST", "/rooms/%s/leave" % room,
                             {"user": user})

    def send(self, room, sender, msg_type, payload, to=None):
        body = {"from": sender, "type": msg_type, "payload": payload}
        if to is not None:
            body["to"] = to
        return self._request("POST", "/rooms/%s/messages" % room, body)

    def poll(self, room, user, since=0):
        path = "/rooms/%s/messages?user=%s&since=%d" % (
            urllib.parse.quote(room), urllib.parse.quote(user), since)
        return self._request("GET", path)["messages"]


def _expect(step, cond, detail=""):
    print("  [%s] %s %s" % ("ok" if cond else "FAIL", step, detail))
    if not cond:
        raise SystemExit("demo failed at: %s" % step)


def run_demo(host="127.0.0.1", port=0):
    """Scripted two-peer call through an ephemeral local server.

    Signalling only -- no audio/video is carried. Each step is
    verified as it happens; any failure exits non-zero.
    """
    server = make_server(host, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    actual_port = server.server_address[1]
    print("signalling server on %s:%d (ephemeral, signalling only -- "
          "no audio/video)" % (host, actual_port))
    try:
        alice = Client("http://%s:%d" % (host, actual_port))
        bob = Client("http://%s:%d" % (host, actual_port))
        room = "demo-room"
        r = alice.join(room, "alice")
        _expect("alice joins, no peers yet", r["peers"] == [])
        r = bob.join(room, "bob")
        _expect("bob joins, sees alice", r["peers"] == ["alice"])
        joined = [m for m in alice.poll(room, "alice")
                  if m["type"] == "peer-joined"]
        _expect("alice sees peer-joined for bob",
                [m["payload"] for m in joined] == [{"user": "bob"}])
        offer = {"sdp": "v=0\r\no=alice 1 1 IN IP4 127.0.0.1\r\n",
                 "type": "offer"}
        alice.send(room, "alice", "offer", offer, to="bob")
        got = [m for m in bob.poll(room, "bob")
               if m["type"] == "offer"]
        _expect("bob receives alice's offer intact",
                len(got) == 1 and got[0]["payload"] == offer
                and got[0]["from"] == "alice")
        answer = {"sdp": "v=0\r\no=bob 1 1 IN IP4 127.0.0.1\r\n",
                  "type": "answer"}
        bob.send(room, "bob", "answer", answer, to="alice")
        got = [m for m in alice.poll(room, "alice")
               if m["type"] == "answer"]
        _expect("alice receives bob's answer intact",
                len(got) == 1 and got[0]["payload"] == answer)
        alice.send(room, "alice", "candidate",
                   {"candidate": "candidate:1 1 udp 1 127.0.0.1 5000"},
                   to="bob")
        bob.send(room, "bob", "candidate",
                 {"candidate": "candidate:1 1 udp 1 127.0.0.1 5001"},
                 to="alice")
        _expect("ICE candidates relayed both ways",
                any(m["type"] == "candidate" for m in
                    bob.poll(room, "bob"))
                and any(m["type"] == "candidate" for m in
                        alice.poll(room, "alice")))
        alice.send(room, "alice", "chat", "hello from alice", to="bob")
        bob.send(room, "bob", "chat", "hello from bob", to="alice")
        _expect("chat messages relayed both ways (Step 3 text proof)",
                any(m["type"] == "chat"
                    and m["payload"] == "hello from alice"
                    for m in bob.poll(room, "bob"))
                and any(m["type"] == "chat"
                        and m["payload"] == "hello from bob"
                        for m in alice.poll(room, "alice")))
        alice.send(room, "alice", "bye", None, to="bob")
        _expect("bob receives bye",
                any(m["type"] == "bye" for m in bob.poll(room, "bob")))
        alice.leave(room, "alice")
        left = [m for m in bob.poll(room, "bob")
                if m["type"] == "peer-left"]
        _expect("bob sees peer-left for alice",
                [m["payload"] for m in left] == [{"user": "alice"}])
        bob.leave(room, "bob")
        _expect("room gone after last leave",
                alice.list_rooms() == [])
        print("demo complete: signalling flow verified end to end "
              "(no media was carried -- see README.md).")
    finally:
        server.shutdown()
        server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Video-chat signalling server (signalling only; "
                    "no audio/video).")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
            ("serve", "start the signalling server"),
            ("demo", "run a scripted two-peer signalling call")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=0 if name == "demo"
                       else 8000)
    args = parser.parse_args(argv)
    if args.command == "serve":
        server = make_server(args.host, args.port)
        print("video-chat signalling server on %s:%d "
              "(signalling only -- no audio/video)"
              % (args.host, server.server_address[1]))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    else:
        run_demo(args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
