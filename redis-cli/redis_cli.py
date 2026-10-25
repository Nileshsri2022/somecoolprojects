#!/usr/bin/env python3
"""Command-line client for a Redis server speaking RESP2 over TCP.

Python 3 standard library only. One-shot mode takes a command;
with no command it enters an interactive REPL.

    python3 redis_cli.py --host 127.0.0.1 -p 6379 PING
    python3 redis_cli.py --host 127.0.0.1 -p 6379 SET key value
    python3 redis_cli.py --host 127.0.0.1 -p 6379   # REPL

The CLI is command-agnostic: anything typed is sent verbatim as a
RESP array of bulk strings, so any server command works. Only
help/quit/exit are handled client-side and never reach the server.
See docs/SPEC.md for the full contract and divergences.
"""

import argparse
import shlex
import socket
import sys

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 6379
DEFAULT_TIMEOUT = 5


class RespError(ValueError):
    """Malformed RESP bytes or a broken connection mid-reply."""


class RedisError(Exception):
    """A server error reply (the `-` RESP type), carried as a value."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------- RESP

def encode_command(args):
    """Encode a command (list of str) as a RESP array of bulk strings."""
    out = [("*%d\r\n" % len(args)).encode("ascii")]
    for arg in args:
        data = arg.encode("utf-8") if isinstance(arg, str) else bytes(arg)
        out.append(("$%d\r\n" % len(data)).encode("ascii"))
        out.append(data)
        out.append(b"\r\n")
    return b"".join(out)


class RespReader:
    """Parse RESP2 values from a buffered byte source.

    `recv` must behave like a socket's: return b"" at EOF. Anything
    else with a compatible `recv(n)` works (tests use a bytes-backed
    stand-in via parse_reply_bytes).
    """

    def __init__(self, recv):
        self._recv = recv
        self._buf = b""

    def _readline(self):
        while b"\r\n" not in self._buf:
            chunk = self._recv(4096)
            if not chunk:
                raise RespError("truncated RESP message")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\r\n", 1)
        return line

    def _read_exact(self, n):
        while len(self._buf) < n:
            chunk = self._recv(4096)
            if not chunk:
                raise RespError("truncated RESP message")
            self._buf += chunk
        data, self._buf = self._buf[:n], self._buf[n:]
        return data

    def read_reply(self):
        line = self._readline()
        if not line:
            raise RespError("empty RESP message")
        prefix, rest = line[:1], line[1:]
        if prefix == b"+":
            return rest.decode("utf-8", errors="replace")
        if prefix == b"-":
            return RedisError(rest.decode("utf-8", errors="replace"))
        if prefix == b":":
            try:
                return int(rest)
            except ValueError:
                raise RespError("malformed integer reply: %r" % line) from None
        if prefix == b"$":
            return self._read_bulk(rest)
        if prefix == b"*":
            return self._read_array(rest)
        raise RespError("unknown RESP type byte: %r" % prefix)

    def _read_length(self, rest, what):
        try:
            length = int(rest)
        except ValueError:
            raise RespError("malformed %s length: %r" % (what, rest)) from None
        if length < -1:
            raise RespError("invalid %s length: %d" % (what, length))
        return length

    def _read_bulk(self, rest):
        length = self._read_length(rest, "bulk string")
        if length == -1:
            return None
        data = self._read_exact(length + 2)
        if data[length:] != b"\r\n":
            raise RespError("bulk string missing trailing CRLF")
        return data[:length].decode("utf-8", errors="replace")

    def _read_array(self, rest):
        length = self._read_length(rest, "array")
        if length == -1:
            return None
        return [self.read_reply() for _ in range(length)]


def parse_reply_bytes(data):
    """Parse exactly one RESP value from bytes (page's TDD examples)."""
    chunks = [data]

    def recv(_n):
        return chunks.pop(0) if chunks else b""

    return RespReader(recv).read_reply()


# ------------------------------------------------------------- formatting

def format_reply(value, indent=0):
    """Render a decoded reply redis-cli style (see docs/SPEC.md)."""
    pad = "  " * indent
    if value is None:
        return pad + "(nil)"
    if isinstance(value, RedisError):
        return pad + "(error) " + value.message
    if isinstance(value, int):
        return pad + "(integer) %d" % value
    if isinstance(value, list):
        if not value:
            return pad + "(empty array)"
        lines = []
        for i, item in enumerate(value):
            rendered = format_reply(item, indent + 1)
            if isinstance(item, list) and item:
                lines.append("%s%d)" % (pad, i + 1))
                lines.append(rendered)
            else:
                lines.append("%s%d) %s" % (pad, i + 1, rendered.strip()))
        return "\n".join(lines)
    return pad + str(value)


# ----------------------------------------------------------------- help

# command -> (usage, summary, since, group). Curated subset; the page
# points at the full Redis commands JSON set (see docs/SPEC.md).
HELP = {
    "ping": ("PING [message]", "Ping the server", "1.0.0", "connection"),
    "echo": ("ECHO message", "Echo the given string", "1.0.0", "connection"),
    "set": ("SET key value [NX|XX] [GET] [EX seconds|PX milliseconds|"
            "EXAT unix-time-seconds|PXAT unix-time-milliseconds|KEEPTTL]",
            "Set the string value of a key", "1.0.0", "string"),
    "get": ("GET key", "Get the value of a key", "1.0.0", "string"),
    "del": ("DEL key [key ...]", "Delete a key", "1.0.0", "generic"),
    "exists": ("EXISTS key [key ...]", "Determine if a key exists",
               "1.0.0", "generic"),
    "incr": ("INCR key", "Increment the integer value of a key by one",
             "1.0.0", "string"),
    "decr": ("DECR key", "Decrement the integer value of a key by one",
             "1.0.0", "string"),
    "lpush": ("LPUSH key element [element ...]",
              "Prepend one or multiple elements to a list", "1.0.0", "list"),
    "rpush": ("RPUSH key element [element ...]",
              "Append one or multiple elements to a list", "1.0.0", "list"),
    "lrange": ("LRANGE key start stop",
               "Get a range of elements from a list", "1.0.0", "list"),
    "llen": ("LLEN key", "Get the length of a list", "1.0.0", "list"),
    "quit": ("QUIT", "Close the connection", "1.0.0", "connection"),
}

HELP_INTRO = (
    'To get help about Redis commands type:\n'
    '      "help @<group>" to get a list of commands in <group>\n'
    '      "help <command>" for help on <command>\n'
    '      "quit" to exit'
)


def help_text(topic=None):
    """Text for `help`, `help <command>` and `help @<group>`."""
    if topic is None:
        return HELP_INTRO
    topic = topic.lower()
    if topic.startswith("@"):
        group = topic[1:]
        names = sorted(n for n, v in HELP.items() if v[3] == group)
        if not names:
            return "(error) unknown group '%s'" % group
        return "\n".join("  " + n.upper() for n in names)
    entry = HELP.get(topic)
    if entry is None:
        return "(error) unknown command '%s'" % topic
    usage, summary, since, group = entry
    return ("  %s\n  summary: %s\n  since: %s\n  group: %s"
            % (usage, summary, since, group))


# Commands that are meaningless with no arguments; bare use in the
# REPL prints the usage hint instead of sending a doomed request.
# PING/QUIT take no arguments, so they are not listed here.
_COMMANDS_NEEDING_ARGS = {
    name for name in HELP if name not in ("ping", "quit")
}


# ---------------------------------------------------------------- client

class RedisClient:
    """One TCP connection to a Redis server, speaking RESP2."""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT,
                 timeout=DEFAULT_TIMEOUT):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock = None
        self._reader = None

    def connect(self):
        try:
            self._sock = socket.create_connection(
                (self.host, self.port), timeout=self.timeout)
        except OSError as exc:
            raise RespError("cannot connect to %s:%s: %s"
                            % (self.host, self.port, exc)) from exc
        self._reader = RespReader(self._sock.recv)
        return self

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
            self._reader = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()
        return False

    def command(self, *args):
        if self._sock is None:
            raise RespError("not connected")
        try:
            self._sock.sendall(encode_command(list(args)))
        except OSError as exc:
            raise RespError("connection lost: %s" % exc) from exc
        try:
            return self._reader.read_reply()
        except OSError as exc:
            raise RespError("connection lost: %s" % exc) from exc


def split_command(line):
    """Split one REPL line with shlex; None for a blank line."""
    stripped = line.strip()
    if not stripped:
        return None
    try:
        parts = shlex.split(stripped)
    except ValueError as exc:
        raise RespError("cannot parse command: %s" % exc) from None
    return parts or None


def run_repl(client, stdin, stdout):
    """REPL loop; streams are injectable so tests need no tty.

    Returns 0 on a clean quit/EOF, 1 if the connection drops.
    """
    prompt = "%s:%s> " % (client.host, client.port)
    while True:
        try:
            stdout.write(prompt)
            stdout.flush()
            line = stdin.readline()
        except KeyboardInterrupt:
            stdout.write("\n")
            return 0
        if line == "":  # EOF (Ctrl-D)
            stdout.write("\n")
            return 0
        line = line.rstrip("\n")
        try:
            parts = split_command(line)
        except RespError as exc:
            stdout.write("(error) %s\n" % exc)
            continue
        if parts is None:
            continue
        word = parts[0].lower()
        if word in ("quit", "exit"):
            return 0
        if word == "help":
            stdout.write(help_text(parts[1] if len(parts) > 1 else None)
                         + "\n")
            continue
        if len(parts) == 1 and word in _COMMANDS_NEEDING_ARGS:
            # Step 5 hint: a bare command that needs arguments shows
            # its usage instead of sending a request bound to fail.
            stdout.write(help_text(word) + "\n")
            continue
        try:
            stdout.write(format_reply(client.command(*parts)) + "\n")
        except RespError as exc:
            stdout.write("(error) %s\n" % exc)
            return 1
        except KeyboardInterrupt:
            stdout.write("\n")
            return 0


# ------------------------------------------------------------------ main

def _rewrite_aliases(argv):
    """Accept the sibling project's `-host`/`-port` spellings."""
    aliases = {"-host": "--host", "-port": "--port", "-timeout": "--timeout"}
    return [aliases.get(arg, arg) for arg in argv]


def build_parser():
    parser = argparse.ArgumentParser(
        prog="redis_cli.py",
        description="Send commands to a Redis server (RESP2). "
                    "With no command, enter an interactive REPL.")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="server host (default: %(default)s)")
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT,
                        help="server port (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="socket timeout in seconds (default: %(default)s)")
    parser.add_argument("command", nargs="*",
                        help="one-shot command, e.g. PING or SET key value")
    return parser


def main(argv=None):
    args = build_parser().parse_args(_rewrite_aliases(
        list(sys.argv[1:] if argv is None else argv)))
    client = RedisClient(args.host, args.port, args.timeout)
    try:
        client.connect()
    except RespError as exc:
        print("(error) %s" % exc, file=sys.stderr)
        return 1
    try:
        if args.command:
            try:
                print(format_reply(client.command(*args.command)))
            except RespError as exc:
                print("(error) %s" % exc, file=sys.stderr)
                return 1
            return 0
        return run_repl(client, sys.stdin, sys.stdout)
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
