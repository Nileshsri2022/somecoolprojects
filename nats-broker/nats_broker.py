#!/usr/bin/env python3
"""Minimal NATS message broker (core text protocol), stdlib only.

Implements the Coding Challenges NATS challenge
(https://codingchallenges.fyi/challenges/challenge-nats/):
INFO on connect, CONNECT, PING/PONG, SUB/UNSUB, PUB/MSG, subject
wildcards (* and >), queue groups, and UNSUB with max_msgs.

Run:  python3 nats_broker.py [--host 127.0.0.1] [--port 4222]
The NATSClient class at the bottom is a minimal client for tests
and for driving the server from Python; it is not a full NATS client.
"""

import argparse
import json
import socket
import threading
import uuid

VERSION = "0.1.0"


def subject_matches(pattern, subject):
    """Return True if a NATS subject matches a subscription pattern.

    '*' matches exactly one token; '>' as the final token matches
    one or more remaining tokens; '>' elsewhere never matches.
    """
    p_tokens = pattern.split(".")
    s_tokens = subject.split(".")
    for i, p in enumerate(p_tokens):
        if p == ">":
            # Only valid as the final token, and it must swallow
            # at least one token (see SPEC.md divergence 3).
            return i == len(p_tokens) - 1 and i < len(s_tokens)
        if i >= len(s_tokens):
            return False
        if p == "*":
            continue
        if p != s_tokens[i]:
            return False
    return len(p_tokens) == len(s_tokens)


class Subscription:
    __slots__ = ("client", "subject", "queue", "sid", "remaining")

    def __init__(self, client, subject, queue, sid):
        self.client = client
        self.subject = subject
        self.queue = queue
        self.sid = sid
        self.remaining = None  # None = unlimited; int = UNSUB max_msgs


class Broker:
    """Subscription registry and delivery. Thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        # client -> {sid: Subscription}
        self._subs = {}
        # (pattern, queue) -> round-robin index
        self._queue_next = {}

    def subscribe(self, client, subject, queue, sid):
        with self._lock:
            per_client = self._subs.setdefault(client, {})
            # Re-subscribing an sid replaces the old subscription,
            # mirroring a fresh SUB for that sid.
            per_client[sid] = Subscription(client, subject, queue, sid)

    def unsubscribe(self, client, sid, max_msgs=None):
        with self._lock:
            per_client = self._subs.get(client)
            if not per_client or sid not in per_client:
                return
            if max_msgs is None:
                del per_client[sid]
            else:
                per_client[sid].remaining = max_msgs

    def remove_client(self, client):
        with self._lock:
            self._subs.pop(client, None)

    def _snapshot(self, subject):
        """Matching subscriptions, partitioned for delivery.

        Returns (plain_subs, queue_groups) where queue_groups maps
        (pattern, queue) -> [Subscription, ...] in insertion order.
        Called with no lock held by publish(); takes the lock itself.
        """
        plain = []
        groups = {}
        with self._lock:
            for per_client in self._subs.values():
                for sub in per_client.values():
                    if not subject_matches(sub.subject, subject):
                        continue
                    if sub.queue is None:
                        plain.append(sub)
                    else:
                        groups.setdefault((sub.subject, sub.queue),
                                          []).append(sub)
        return plain, groups

    def publish(self, subject, reply_to, payload):
        """Deliver one message. Returns the number of deliveries."""
        plain, groups = self._snapshot(subject)
        deliveries = []

        for sub in plain:
            deliveries.append(sub)

        # Queue groups: exactly one member per matching group,
        # round-robin over the members that match this subject.
        with self._lock:
            for key, members in groups.items():
                if not members:
                    continue
                idx = self._queue_next.get(key, 0) % len(members)
                self._queue_next[key] = idx + 1
                deliveries.append(members[idx])

        sent = 0
        expired = []
        for sub in deliveries:
            if sub.client.send_msg(subject, sub.sid, reply_to, payload):
                sent += 1
            # Count a delivery against UNSUB max_msgs even if the
            # send failed: the message was routed to this sub.
            if sub.remaining is not None:
                sub.remaining -= 1
                if sub.remaining <= 0:
                    expired.append(sub)
        if expired:
            with self._lock:
                for sub in expired:
                    per_client = self._subs.get(sub.client)
                    if per_client and per_client.get(sub.sid) is sub:
                        del per_client[sub.sid]
        return sent


class ClientHandler(threading.Thread):
    """One thread per TCP connection."""

    def __init__(self, conn, addr, broker, host, port):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.broker = broker
        self.host = host
        self.port = port
        self._send_lock = threading.Lock()
        self._rfile = conn.makefile("rwb")
        self.alive = True

    # -- outbound -------------------------------------------------
    def send_line(self, line):
        """Send one CRLF-terminated line. False if the peer is gone."""
        if isinstance(line, str):
            line = line.encode()
        with self._send_lock:
            try:
                self.conn.sendall(line + b"\r\n")
                return True
            except OSError:
                return False

    def send_msg(self, subject, sid, reply_to, payload):
        header = "MSG %s %d" % (subject, sid)
        if reply_to:
            header += " " + reply_to
        header += " %d" % len(payload)
        with self._send_lock:
            try:
                self.conn.sendall(header.encode() + b"\r\n"
                                  + payload + b"\r\n")
                return True
            except OSError:
                return False

    def _err(self, msg):
        self.send_line("-ERR '%s'" % msg)

    # -- inbound --------------------------------------------------
    def _read_line(self):
        """One protocol line, without trailing CRLF/LF. None on EOF."""
        raw = self._rfile.readline()
        if not raw:
            return None
        return raw.rstrip(b"\r\n").decode("utf-8", "replace")

    def _read_exact(self, size):
        """Exactly size bytes, then the trailing CRLF. None on EOF."""
        data = self._rfile.read(size)
        if len(data) < size:
            return None
        trailer = self._rfile.read(2)
        if trailer == b"\r\n":
            return data
        # Tolerate a lone LF trailer; anything else means the stream
        # is out of sync, but the payload itself was read correctly.
        if trailer[:1] == b"\n":
            return data
        return data

    def run(self):
        info = {
            "server_id": uuid.uuid4().hex,
            "version": VERSION,
            "host": self.host,
            "port": self.port,
            "client_ip": self.addr[0],
        }
        self.send_line("INFO " + json.dumps(info))
        try:
            while self.alive:
                line = self._read_line()
                if line is None:
                    break
                if line == "":
                    continue
                if not self._dispatch(line):
                    break
        except OSError:
            pass
        finally:
            self.broker.remove_client(self)
            self.alive = False
            try:
                self.conn.close()
            except OSError:
                pass

    def _dispatch(self, line):
        parts = line.split(" ")
        verb = parts[0].upper()

        if verb == "CONNECT":
            rest = line[len("CONNECT"):].strip()
            try:
                json.loads(rest) if rest else {}
            except ValueError:
                self._err("Invalid CONNECT")
                return True
            self.send_line("+OK")
            return True

        if verb == "PING":
            self.send_line("PONG")
            return True

        if verb == "PONG":
            return True  # client heartbeat reply; nothing to send

        if verb == "SUB":
            # SUB <subject> [queue] <sid>
            args = parts[1:]
            try:
                if len(args) == 2:
                    subject, sid = args
                    queue = None
                elif len(args) == 3:
                    subject, queue, sid = args
                else:
                    raise ValueError
                sid = int(sid)
            except ValueError:
                self._err("Invalid SUB")
                return True
            self.broker.subscribe(self, subject, queue, sid)
            self.send_line("+OK")
            return True

        if verb == "UNSUB":
            args = parts[1:]
            try:
                sid = int(args[0])
                max_msgs = int(args[1]) if len(args) > 1 else None
                if len(args) > 2:
                    raise ValueError
            except (ValueError, IndexError):
                self._err("Invalid UNSUB")
                return True
            self.broker.unsubscribe(self, sid, max_msgs)
            self.send_line("+OK")
            return True

        if verb == "PUB":
            # PUB <subject> [reply-to] <size>
            args = parts[1:]
            try:
                if len(args) == 2:
                    subject, size = args
                    reply_to = None
                elif len(args) == 3:
                    subject, reply_to, size = args
                else:
                    raise ValueError
                size = int(size)
                if size < 0:
                    raise ValueError
            except ValueError:
                self._err("Invalid PUB")
                return True
            payload = self._read_exact(size)
            if payload is None:
                return False
            # +OK first, matching the page's Step 3 transcript
            # (+OK, then MSG), even when publisher == subscriber.
            self.send_line("+OK")
            self.broker.publish(subject, reply_to, payload)
            return True

        self._err("Unknown Protocol Operation")
        return True


class NATSServer:
    """Listening socket + accept loop. Start with serve_forever()."""

    def __init__(self, host="127.0.0.1", port=4222):
        self.host = host
        self.broker = Broker()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self.port = self._sock.getsockname()[1]
        self._sock.listen(128)
        self._sock.settimeout(0.2)
        self._stop = threading.Event()
        self._thread = None

    def serve_forever(self):
        while not self._stop.is_set():
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            ClientHandler(conn, addr, self.broker,
                          self.host, self.port).start()

    def start(self):
        self._thread = threading.Thread(target=self.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)


# ------------------------------------------------------------------
# Minimal client (for tests and interactive use; not a full client)
# ------------------------------------------------------------------

class NATSClient:
    def __init__(self, host="127.0.0.1", port=4222, timeout=5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        self._rfile = None
        self.info = None
        # MSGs that arrived while waiting for a +OK/PONG ack; they
        # must not be lost, so read_msg() returns them first.
        self._pending = []

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port),
                                             timeout=self.timeout)
        self._rfile = self.sock.makefile("rwb")
        line = self._read_line(timeout=self.timeout)
        if not line.startswith("INFO "):
            raise ValueError("expected INFO, got %r" % line)
        self.info = json.loads(line[5:])
        self._send_line("CONNECT {}")
        self._read_ack()
        return self

    def close(self):
        try:
            if self._rfile is not None:
                self._rfile.close()
        except OSError:
            pass
        try:
            if self.sock is not None:
                self.sock.close()
        except OSError:
            pass
        self.sock = None
        self._rfile = None

    def _send_line(self, line):
        self.sock.sendall(line.encode() + b"\r\n")

    def _read_line(self, timeout=None):
        if timeout is not None:
            self.sock.settimeout(timeout)
        raw = self._rfile.readline()
        if not raw:
            raise ConnectionError("server closed the connection")
        return raw.rstrip(b"\r\n").decode("utf-8", "replace")

    def _parse_msg(self, line):
        parts = line.split(" ")
        # MSG <subject> <sid> [reply-to] <size>
        if len(parts) == 4:
            _, subject, sid, size = parts
            reply_to = None
        elif len(parts) == 5:
            _, subject, sid, reply_to, size = parts
        else:
            raise ValueError("malformed MSG: %r" % line)
        size = int(size)
        payload = self._rfile.read(size)
        self._rfile.read(2)  # trailing CRLF
        return subject, int(sid), reply_to, payload

    def _read_ack(self, want="+OK"):
        """Consume lines until `want`, buffering any MSG frames."""
        while True:
            line = self._read_line(timeout=self.timeout)
            if line.startswith("MSG "):
                self._pending.append(self._parse_msg(line))
            elif line == want:
                return
            elif line.startswith("-ERR"):
                raise ValueError("server error: %s" % line)
            # Other lines (+OK while waiting for PONG, etc.) ignored.

    def ping(self):
        self._send_line("PING")
        self._read_ack(want="PONG")
        return True

    def subscribe(self, subject, sid, queue=None):
        if queue:
            self._send_line("SUB %s %s %d" % (subject, queue, sid))
        else:
            self._send_line("SUB %s %d" % (subject, sid))
        self._read_ack()

    def unsubscribe(self, sid, max_msgs=None):
        if max_msgs is None:
            self._send_line("UNSUB %d" % sid)
        else:
            self._send_line("UNSUB %d %d" % (sid, max_msgs))
        self._read_ack()

    def publish(self, subject, payload, reply_to=None):
        if isinstance(payload, str):
            payload = payload.encode()
        if reply_to:
            self._send_line("PUB %s %s %d"
                            % (subject, reply_to, len(payload)))
        else:
            self._send_line("PUB %s %d" % (subject, len(payload)))
        self.sock.sendall(payload + b"\r\n")
        self._read_ack()

    def read_msg(self, timeout=2.0):
        """Next MSG as (subject, sid, reply_to, payload).

        Returns buffered MSGs first. Raises TimeoutError if nothing
        arrives within `timeout` seconds.
        """
        if self._pending:
            return self._pending.pop(0)
        while True:
            try:
                line = self._read_line(timeout=timeout)
            except socket.timeout:
                raise TimeoutError("no MSG within %.1fs" % timeout)
            if line.startswith("MSG "):
                return self._parse_msg(line)
            # +OK / PONG lines are not messages; keep waiting.


def main():
    parser = argparse.ArgumentParser(description="Minimal NATS broker")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4222)
    args = parser.parse_args()
    server = NATSServer(args.host, args.port)
    print("nats-broker listening on %s:%d" % (args.host, server.port),
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
