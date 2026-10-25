"""Discord bot (Coding Challenges: Build Your Own Discord Bot).

Python 3 standard library only. Implements the challenge steps
(Hello greeting, !quote, !challenge, !add, !list) on top of a
minimal Discord Gateway (WebSocket) client and the REST
send-message endpoint.

Live use needs the user's own bot token, read at run time from
the DISCORD_BOT_TOKEN environment variable only. No token is
hardcoded, defaulted, or printed anywhere in this file. See
README.md and docs/ for the Step Zero setup (Developer Portal,
MESSAGE CONTENT INTENT, invite URL) and Step 5 hosting notes.
"""

import argparse
import base64
import html
import json
import os
import random
import re
import socket
import ssl
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
API_BASE = "https://discord.com/api/v10"
QUOTE_URL = "https://dummyjson.com/quotes/random"
TOKEN_ENV_VAR = "DISCORD_BOT_TOKEN"

INTENT_GUILDS = 1 << 0
INTENT_GUILD_MESSAGES = 1 << 9
INTENT_MESSAGE_CONTENT = 1 << 15
INTENTS = INTENT_GUILDS | INTENT_GUILD_MESSAGES | INTENT_MESSAGE_CONTENT

MAX_MESSAGE_LENGTH = 2000
MAX_FRAME_PAYLOAD = 16 * 1024 * 1024  # safety bound, see DESIGN.md

OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_RESUME = 6
OP_RECONNECT = 7
OP_INVALID_SESSION = 9
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11

WS_CONTINUATION = 0
WS_TEXT = 1
WS_CLOSE = 8
WS_PING = 9
WS_PONG = 10


# ---------------------------------------------------------------------------
# WebSocket framing (minimal subset: text, ping/pong, close, fragmentation)
# ---------------------------------------------------------------------------

def ws_encode_frame(payload, opcode=WS_TEXT, mask=None):
    """Encode one client frame. mask=None -> random mask (real use);
    tests pass an explicit 4-byte mask for deterministic output."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if mask is None:
        mask = os.urandom(4)
    header = bytes([0x80 | opcode])
    length = len(payload)
    mask_bit = 0x80
    if length < 126:
        header += bytes([mask_bit | length])
    elif length < 65536:
        header += bytes([mask_bit | 126]) + struct.pack("!H", length)
    else:
        header += bytes([mask_bit | 127]) + struct.pack("!Q", length)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return header + mask + masked


class FrameParser:
    """Incremental server-frame parser. feed() returns a list of
    (opcode, payload_bytes); fragmented text frames are reassembled
    and reported once, with opcode WS_TEXT."""

    def __init__(self):
        self._buf = b""
        self._fragments = []

    def feed(self, data):
        self._buf += data
        messages = []
        while True:
            parsed = self._try_parse_one()
            if parsed is None:
                break
            opcode, fin, payload = parsed
            if opcode == WS_CONTINUATION or (not fin and opcode == WS_TEXT):
                self._fragments.append(payload)
                if fin:
                    messages.append((WS_TEXT, b"".join(self._fragments)))
                    self._fragments = []
            elif opcode in (WS_TEXT, WS_PING, WS_CLOSE, WS_PONG):
                messages.append((opcode, payload))
            # Binary frames and anything else: ignored by design.
        return messages

    def _try_parse_one(self):
        buf = self._buf
        if len(buf) < 2:
            return None
        fin = bool(buf[0] & 0x80)
        opcode = buf[0] & 0x0F
        masked = bool(buf[1] & 0x80)
        length = buf[1] & 0x7F
        pos = 2
        if length == 126:
            if len(buf) < pos + 2:
                return None
            length = struct.unpack("!H", buf[pos:pos + 2])[0]
            pos += 2
        elif length == 127:
            if len(buf) < pos + 8:
                return None
            length = struct.unpack("!Q", buf[pos:pos + 8])[0]
            pos += 8
        if length > MAX_FRAME_PAYLOAD:
            raise ValueError("websocket frame payload too large")
        if masked:
            if len(buf) < pos + 4:
                return None
            mask = buf[pos:pos + 4]
            pos += 4
        if len(buf) < pos + length:
            return None
        payload = buf[pos:pos + length]
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self._buf = buf[pos + length:]
        return opcode, fin, payload


def ws_handshake_request(host, path):
    """Build the HTTP Upgrade request; returns (request_bytes, key)."""
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    lines = [
        "GET %s HTTP/1.1" % path,
        "Host: %s" % host,
        "Upgrade: websocket",
        "Connection: Upgrade",
        "Sec-WebSocket-Key: %s" % key,
        "Sec-WebSocket-Version: 13",
        "",
        "",
    ]
    return "\r\n".join(lines).encode("ascii"), key


# ---------------------------------------------------------------------------
# Gateway payloads / heartbeat / backoff (pure, unit-testable)
# ---------------------------------------------------------------------------

def identify_payload(token):
    return {
        "op": OP_IDENTIFY,
        "d": {
            "token": token,
            "intents": INTENTS,
            "properties": {
                "os": sys.platform,
                "browser": "discord_bot",
                "device": "discord_bot",
            },
        },
    }


def resume_payload(token, session_id, seq):
    return {
        "op": OP_RESUME,
        "d": {"token": token, "session_id": session_id, "seq": seq},
    }


def heartbeat_payload(seq):
    return {"op": OP_HEARTBEAT, "d": seq}


def should_heartbeat(now, last_heartbeat, interval_ms):
    if last_heartbeat is None:
        return True
    return (now - last_heartbeat) * 1000 >= interval_ms


def backoff_seconds(attempt):
    return min(30, 2 ** attempt)


# ---------------------------------------------------------------------------
# Challenge catalogue
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def extract_title(html_text):
    match = _TITLE_RE.search(html_text)
    if not match:
        raise ValueError("no <title> tag found")
    title = html.unescape(match.group(1))
    title = re.sub(r"\s+", " ", title).strip()
    suffix = " | Coding Challenges"
    if title.endswith(suffix):
        title = title[: -len(suffix)].strip()
    if not title:
        raise ValueError("empty <title> tag")
    return title


def is_valid_challenge_url(url):
    """True only for a challenge page on codingchallenges.fyi itself.
    Host is compared exactly (parsed netloc), never by substring."""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.netloc not in ("codingchallenges.fyi", "www.codingchallenges.fyi"):
        return False
    return parsed.path.startswith("/challenges/challenge-")


class ChallengeCatalogue:
    def __init__(self, path):
        self.path = path
        self.challenges = []

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            self.challenges = []
            return self.challenges
        if not isinstance(data, list):
            self.challenges = []
            return self.challenges
        self.challenges = [
            {"title": str(c["title"]), "url": str(c["url"])}
            for c in data
            if isinstance(c, dict) and "title" in c and "url" in c
        ]
        return self.challenges

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.challenges, f, indent=2)
            f.write("\n")
        os.replace(tmp, self.path)

    def random_challenge(self, rng=None):
        if not self.challenges:
            return None
        return (rng or random).choice(self.challenges)

    def add(self, url, title_fetcher):
        """Validate, fetch title, append + save. Returns (ok, message)."""
        if not is_valid_challenge_url(url):
            return False, (
                "That doesn't look like a valid Coding Challenges "
                "challenge URL. It should look like "
                "https://codingchallenges.fyi/challenges/challenge-..."
            )
        if any(c["url"] == url for c in self.challenges):
            return False, "That challenge is already listed."
        try:
            title = extract_title(title_fetcher(url))
        except Exception:
            return False, "I couldn't read the title of that challenge page."
        self.challenges.append({"title": title, "url": url})
        self.save()
        return True, "Added: %s — %s" % (title, url)

    def list_text(self):
        if not self.challenges:
            return "No challenges yet."
        lines = ["Challenges:"]
        for i, c in enumerate(self.challenges, 1):
            lines.append("%d. %s — %s" % (i, c["title"], c["url"]))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Quote fetching
# ---------------------------------------------------------------------------

def default_json_fetcher(url):
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.load(resp)


def fetch_quote(fetcher=None):
    data = (fetcher or default_json_fetcher)(QUOTE_URL)
    quote = data.get("quote")
    author = data.get("author")
    if not quote or not author:
        raise ValueError("quote API response missing quote/author")
    return '"%s" — %s' % (quote, author)


def default_html_fetcher(url):
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# REST send-message
# ---------------------------------------------------------------------------

def build_send_request(channel_id, content, token):
    if len(content) > MAX_MESSAGE_LENGTH:
        raise ValueError("message exceeds Discord's 2000-character limit")
    url = "%s/channels/%s/messages" % (API_BASE, channel_id)
    body = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", "Bot %s" % token)
    req.add_header("Content-Type", "application/json")
    return req


def send_message(channel_id, content, token, urlopen=None):
    opener = urlopen or urllib.request.urlopen
    with opener(build_send_request(channel_id, content, token), timeout=15) as resp:
        return json.load(resp)


# ---------------------------------------------------------------------------
# Command dispatch (pure apart from the injected fetchers/catalogue)
# ---------------------------------------------------------------------------

HELP_TEXT = (
    "Commands: Hello | !quote | !challenge | !list | !add <challenge URL>"
)


class Dispatcher:
    def __init__(self, catalogue, bot_id=None,
                 quote_fetcher=None, title_fetcher=None, rng=None):
        self.catalogue = catalogue
        self.bot_id = bot_id
        self.quote_fetcher = quote_fetcher
        self.title_fetcher = title_fetcher or default_html_fetcher
        self.rng = rng

    def handle_message(self, event):
        """MESSAGE_CREATE payload -> reply string or None."""
        author = event.get("author") or {}
        if author.get("bot"):
            return None
        if self.bot_id is not None and author.get("id") == self.bot_id:
            return None
        content = event.get("content")
        if not isinstance(content, str):
            return None
        stripped = content.strip()
        if stripped.lower() == "hello":
            username = author.get("username") or "there"
            return "Hello, %s!" % username
        if not stripped.startswith("!"):
            return None
        parts = stripped.split(None, 1)
        command = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if command == "!quote":
            try:
                return fetch_quote(self.quote_fetcher)
            except Exception:
                return "Sorry, I couldn't fetch a quote right now."
        if command == "!challenge":
            entry = self.catalogue.random_challenge(self.rng)
            if entry is None:
                return "No challenges in the catalogue yet."
            return "%s — %s" % (entry["title"], entry["url"])
        if command == "!list":
            return self.catalogue.list_text()
        if command == "!add":
            if not arg:
                return "Usage: !add <challenge URL>"
            ok, message = self.catalogue.add(arg, self.title_fetcher)
            return message
        if command == "!help":
            return HELP_TEXT
        return None  # unknown !-command: stay silent


# ---------------------------------------------------------------------------
# Gateway client (socket-injectable for tests)
# ---------------------------------------------------------------------------

class GatewayClient:
    def __init__(self, token, dispatcher, send_message_fn,
                 gateway_url=GATEWAY_URL):
        self.token = token
        self.dispatcher = dispatcher
        self.send_message_fn = send_message_fn
        self.gateway_url = gateway_url
        self.sock = None
        self.parser = FrameParser()
        self.seq = None
        self.session_id = None
        self.heartbeat_interval_ms = None
        self.last_heartbeat = None
        self.ack_pending = False
        self.reconnect_requested = False
        self.identified = False

    # -- wire helpers ------------------------------------------------------
    def send_json(self, payload):
        self.sock.sendall(ws_encode_frame(json.dumps(payload)))

    def _send_pong(self, payload):
        self.sock.sendall(ws_encode_frame(payload, opcode=WS_PONG))

    def connect(self, sock_factory=None):
        parsed = urllib.parse.urlparse(self.gateway_url)
        host = parsed.hostname
        port = parsed.port or 443
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        raw = (sock_factory or socket.create_connection)((host, port), timeout=15)
        ctx = ssl.create_default_context()
        self.sock = ctx.wrap_socket(raw, server_hostname=host)
        request, _key = ws_handshake_request(host, path)
        self.sock.sendall(request)
        # Read until the end of the HTTP response headers.
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("gateway closed during handshake")
            buf += chunk
        if b"101" not in buf.split(b"\r\n", 1)[0]:
            raise ConnectionError("gateway handshake failed: %r" % buf[:200])
        self.sock.settimeout(1.0)

    def handle_payload(self, payload):
        """One gateway JSON payload. Returns True to keep running."""
        op = payload.get("op")
        if op == OP_DISPATCH:
            self.seq = payload.get("s", self.seq)
            event = payload.get("t")
            data = payload.get("d") or {}
            if event == "READY":
                self.session_id = data.get("session_id")
                user = data.get("user") or {}
                self.dispatcher.bot_id = user.get("id")
            elif event == "MESSAGE_CREATE":
                reply = self.dispatcher.handle_message(data)
                if reply is not None:
                    self.send_message_fn(data.get("channel_id"), reply)
            return True
        if op == OP_HELLO:
            self.heartbeat_interval_ms = (payload.get("d") or {}).get(
                "heartbeat_interval")
            self._heartbeat(now=time.time(), force=True)
            if self.session_id is not None and self.seq is not None:
                self.send_json(resume_payload(self.token, self.session_id,
                                              self.seq))
            else:
                self.send_json(identify_payload(self.token))
            self.identified = True
            return True
        if op == OP_HEARTBEAT:
            self._heartbeat(now=time.time(), force=True)
            return True
        if op == OP_HEARTBEAT_ACK:
            self.ack_pending = False
            return True
        if op == OP_RECONNECT:
            self.reconnect_requested = True
            return False
        if op == OP_INVALID_SESSION:
            resumable = payload.get("d")
            if not resumable:
                self.session_id = None
                self.seq = None
            self.reconnect_requested = True
            return False
        return True

    def _heartbeat(self, now, force=False):
        if self.heartbeat_interval_ms is None:
            return
        if not force and not should_heartbeat(now, self.last_heartbeat,
                                              self.heartbeat_interval_ms):
            return
        if self.ack_pending and not force:
            # Missed ACK: the connection is dead.
            self.reconnect_requested = True
            return
        self.send_json(heartbeat_payload(self.seq))
        self.last_heartbeat = now
        self.ack_pending = True

    def step(self):
        """One loop iteration: recv + process, plus due heartbeat.
        Returns False when the client should stop (reconnect/close)."""
        if self.heartbeat_interval_ms is not None:
            self._heartbeat(now=time.time())
            if self.reconnect_requested:
                return False
        try:
            data = self.sock.recv(65536)
        except socket.timeout:
            return not self.reconnect_requested
        except OSError:
            return False
        if not data:
            return False
        for opcode, payload in self.parser.feed(data):
            if opcode == WS_PING:
                self._send_pong(payload)
            elif opcode == WS_CLOSE:
                return False
            elif opcode == WS_TEXT:
                try:
                    message = json.loads(payload.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                if not self.handle_payload(message):
                    return False
        return not self.reconnect_requested

    def run(self):
        attempt = 0
        while True:
            self.reconnect_requested = False
            self.parser = FrameParser()
            self.ack_pending = False
            try:
                self.connect()
                while self.step():
                    pass
            except (OSError, ConnectionError, ValueError):
                pass
            finally:
                try:
                    if self.sock is not None:
                        self.sock.close()
                except OSError:
                    pass
                self.sock = None
            delay = backoff_seconds(attempt)
            attempt += 1
            print("reconnecting in %ds..." % delay, file=sys.stderr)
            time.sleep(delay)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Discord bot (stdlib only)")
    parser.add_argument("--catalogue", default="challenges.json")
    parser.add_argument("--gateway-url", default=GATEWAY_URL)
    args = parser.parse_args(argv)
    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        print("error: set the %s environment variable to your bot token "
              "(see README.md, Step Zero)" % TOKEN_ENV_VAR, file=sys.stderr)
        return 2
    catalogue = ChallengeCatalogue(args.catalogue)
    catalogue.load()
    dispatcher = Dispatcher(catalogue)

    def _send(channel_id, content):
        send_message(channel_id, content, token)

    client = GatewayClient(token, dispatcher, _send,
                           gateway_url=args.gateway_url)
    client.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
