"""Minimal raw-socket IRC client (Coding Challenges #16).

Python 3 standard library only. Implements the challenge's
subset of RFC 2812: register with NICK/USER, answer PING with
PONG, join/part one channel, change nick, send/receive
PRIVMSG, and quit politely.

Usage:
    python3 irc_client.py --host 127.0.0.1 --port 6667 \\
        --nick CCClient --channel '#cc'

    /join #cc     join a channel
    /part         leave the current channel
    /nick NewNick change nickname
    /quit [msg]   leave IRC
    <text>        send <text> to the current channel
"""

import argparse
import socket
import sys
import threading


def parse_message(line):
    """Parse one IRC line into a Message, or None for blank lines.

    Trailing parameter (after ' :') is kept whole, including
    any further ':' characters inside it.
    """
    line = line.rstrip("\r\n")
    if not line.strip():
        return None
    prefix = None
    rest = line
    if rest.startswith(":"):
        prefix, _, rest = rest[1:].partition(" ")
        if not rest:
            return Message(prefix=prefix, command="", params=[])
    params = []
    while rest:
        if rest.startswith(":"):
            params.append(rest[1:])
            break
        token, sep, rest = rest.partition(" ")
        params.append(token)
        if not sep:
            break
    if not params:
        return Message(prefix=prefix, command="", params=[])
    return Message(prefix=prefix, command=params[0], params=params[1:])


def nick_of(prefix):
    """Nick part of a 'nick!user@host' prefix, or the prefix itself."""
    if not prefix:
        return ""
    return prefix.split("!", 1)[0]


class Message:
    __slots__ = ("prefix", "command", "params")

    def __init__(self, prefix, command, params):
        self.prefix = prefix
        self.command = command
        self.params = params

    def __eq__(self, other):
        return (
            isinstance(other, Message)
            and self.prefix == other.prefix
            and self.command == other.command
            and self.params == other.params
        )

    def __repr__(self):
        return (
            f"Message(prefix={self.prefix!r}, command={self.command!r}, "
            f"params={self.params!r})"
        )


class IRCClient:
    """IRC state machine. Socket I/O is kept behind send_line so
    tests can drive handle_line/handle_user_input without a socket."""

    def __init__(self, nick, username="guest",
                 realname="Coding Challenges Client",
                 host="127.0.0.1", port=6667, channel=None,
                 display=None):
        self.nick = nick
        self.username = username
        self.realname = realname
        self.host = host
        self.port = port
        self.pending_channel = channel
        self.current_channel = None
        self.registered = False
        self.display = display if display is not None else print
        self._buffer = b""
        self._sock = None
        self._send = None  # injected callable(line) used by tests
        self._stop = threading.Event()
        self._receiver = None

    # -- sending ------------------------------------------------

    def send_line(self, line):
        """Send one raw line (CRLF added). Returns the line sent."""
        if self._send is not None:
            self._send(line)
        elif self._sock is not None:
            self._sock.sendall((line + "\r\n").encode("utf-8", "replace"))
        return line

    # -- receiving ----------------------------------------------

    def feed_bytes(self, data):
        """Feed raw bytes; return outgoing lines for complete lines."""
        self._buffer += data
        outgoing = []
        while b"\n" in self._buffer:
            raw, self._buffer = self._buffer.split(b"\n", 1)
            outgoing.extend(self.handle_line(raw.decode("utf-8", "replace")))
        return outgoing

    def handle_line(self, line):
        """Handle one server line. Returns lines to send back."""
        msg = parse_message(line)
        if msg is None:
            return []
        outgoing = []
        cmd = msg.command
        params = msg.params

        if cmd == "PING":
            token = params[0] if params else ""
            outgoing.append(self._pong(token))
            return outgoing

        if cmd == "001":
            self.registered = True
            if params:
                self.display(" ".join(params[1:]) if len(params) > 1
                             else params[0])
            if self.pending_channel:
                channel = self.pending_channel
                self.pending_channel = None
                outgoing.append(self._join(channel))
            return outgoing

        if cmd in ("002", "003", "004", "375", "372", "376"):
            if params:
                self.display(params[-1])
            return outgoing

        if cmd == "NOTICE":
            text = params[-1] if params else ""
            sender = nick_of(msg.prefix)
            if msg.prefix and "!" in msg.prefix:
                self.display(f"{sender}: {text}")
            else:
                self.display(f"* {text}")
            return outgoing

        if cmd == "353":  # NAMES reply: params = [me, =, channel, names]
            if len(params) >= 4:
                self.display(f"Users on {params[2]}: {params[3]}")
            return outgoing

        if cmd == "366":  # end of NAMES: nothing new to show
            return outgoing

        if cmd == "433":  # nickname in use
            taken = params[1] if len(params) > 1 else self.nick
            self.display(f"Nickname {taken} is already in use")
            return outgoing

        if cmd == "ERROR":
            self.display(f"Error: {params[-1] if params else ''}")
            return outgoing

        if cmd == "JOIN":
            channel = params[0] if params else ""
            sender = nick_of(msg.prefix)
            if sender == self.nick:
                self.current_channel = channel
                self.display(f"You joined {channel}")
            else:
                self.display(f"{sender} joined {channel}")
            return outgoing

        if cmd == "PART":
            channel = params[0] if params else ""
            reason = params[1] if len(params) > 1 else ""
            sender = nick_of(msg.prefix)
            suffix = f" ({reason})" if reason else ""
            if sender == self.nick:
                self.current_channel = None
                self.display(f"You left {channel}{suffix}")
            else:
                self.display(f"{sender} left {channel}{suffix}")
            return outgoing

        if cmd == "NICK":
            new = params[0] if params else ""
            sender = nick_of(msg.prefix)
            if sender == self.nick:
                self.nick = new
            self.display(f"{sender} is now known as {new}")
            return outgoing

        if cmd == "PRIVMSG":
            if len(params) >= 2:
                self.display(f"{nick_of(msg.prefix)}: {params[1]}")
            return outgoing

        if cmd == "QUIT":
            reason = params[0] if params else ""
            text = f"{nick_of(msg.prefix)} has left IRC"
            if reason:
                text += f" {reason}"
            self.display(text)
            return outgoing

        # Anything else: show it raw rather than dropping it.
        self.display(line.rstrip("\r\n"))
        return outgoing

    # -- user input ---------------------------------------------

    def handle_user_input(self, text):
        """Map one input line to (outgoing_lines, error).

        Exactly one of the two is non-empty, except empty input
        which yields ([], '')."""
        text = text.rstrip("\r\n")
        if not text.strip():
            return [], ""
        if text.startswith("/"):
            parts = text[1:].split(None, 1)
            command = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            if command == "join":
                channel = arg.strip().split()[0] if arg.strip() else ""
                if not channel or channel[0] not in "#&":
                    return [], "Usage: /join #channel"
                return [self._join(channel)], ""
            if command == "part":
                if not self.current_channel:
                    return [], "You are not on a channel"
                return [f"PART {self.current_channel}"], ""
            if command == "nick":
                new = arg.strip().split()[0] if arg.strip() else ""
                if not new:
                    return [], "Usage: /nick NewNickname"
                return [f"NICK {new}"], ""
            if command == "quit":
                if arg.strip():
                    return [f"QUIT :{arg.strip()}"], ""
                return ["QUIT"], ""
            return [], f"Unknown command: /{command}"
        if not self.current_channel:
            return [], "You are not on a channel (use /join #channel first)"
        return [f"PRIVMSG {self.current_channel} :{text}"], ""

    # -- small send helpers (also used for outgoing replies) ----

    def _pong(self, token):
        line = f"PONG :{token}" if token else "PONG"
        return line

    def _join(self, channel):
        return f"JOIN {channel}"

    # -- network loop -------------------------------------------

    def connect(self):
        self._sock = socket.create_connection((self.host, self.port),
                                              timeout=10)
        self.send_line(f"NICK {self.nick}")
        self.send_line(f"USER {self.username} 0 * :{self.realname}")
        self._receiver = threading.Thread(target=self._receive_loop,
                                          daemon=True)
        self._receiver.start()

    def _receive_loop(self):
        try:
            while not self._stop.is_set():
                data = self._sock.recv(4096)
                if not data:
                    self.display("Connection closed by server")
                    break
                for line in self.feed_bytes(data):
                    self.send_line(line)
        except OSError as exc:
            if not self._stop.is_set():
                self.display(f"Connection error: {exc}")
        finally:
            self._stop.set()

    def run(self):
        """Connect, then read stdin until /quit, EOF, or Ctrl-C."""
        self.connect()
        try:
            for line in sys.stdin:
                outgoing, error = self.handle_user_input(line)
                if error:
                    print(error, file=sys.stderr)
                    continue
                for out in outgoing:
                    self.send_line(out)
                if outgoing and outgoing[0].startswith("QUIT"):
                    break
        except KeyboardInterrupt:
            self.send_line("QUIT :Interrupted")
        finally:
            self._stop.set()
            if self._sock is not None:
                try:
                    self._sock.close()
                except OSError:
                    pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Minimal IRC client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6667)
    parser.add_argument("--nick", default="CCClient")
    parser.add_argument("--username", default="guest")
    parser.add_argument("--realname", default="Coding Challenges Client")
    parser.add_argument("--channel", default=None,
                        help="channel to join after registration, e.g. #cc")
    args = parser.parse_args(argv)
    client = IRCClient(nick=args.nick, username=args.username,
                       realname=args.realname, host=args.host,
                       port=args.port, channel=args.channel)
    client.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
