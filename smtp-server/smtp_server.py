#!/usr/bin/env python3
"""A minimal SMTP server (Coding Challenges: Build Your Own SMTP Server).

Python 3 standard library only. Speaks enough of RFC 5321 for an SMTP
client to deliver mail: greeting, HELO/EHLO, MAIL FROM, RCPT TO, DATA
(with dot-unstuffing), RSET, NOOP, QUIT. Accepted messages are stored
in memory and, when --maildir is given, also as one .eml file each.
No relaying, authentication, TLS, or retrieval protocol is provided.

Usage:
    python3 smtp_server.py [--host 127.0.0.1] [--port 2525]
                           [--maildir DIR]

The default port is 2525 (port 25 needs root); pass --port 25 when
running privileged if you want the textbook port.
"""

import argparse
import os
import socketserver
import sys
import threading
from dataclasses import dataclass, field

GREETING = "CC SMTP Server"


@dataclass
class Message:
    """One accepted message: envelope plus DATA content."""

    mail_from: str
    rcpt_tos: list = field(default_factory=list)
    data: str = ""


def parse_address(arg):
    """Parse an address argument after MAIL FROM: / RCPT TO:.

    Accepts <addr@example.com>, <> (null reverse-path), and a bare
    addr@example.com. Anything else, or an address without exactly
    one '@' with non-empty sides, raises ValueError.
    """
    arg = arg.strip()
    if arg.startswith("<"):
        if not arg.endswith(">"):
            raise ValueError("unclosed angle brackets")
        inner = arg[1:-1]
        if inner == "":
            return ""  # null reverse-path
        addr = inner
    else:
        if not arg or any(c.isspace() for c in arg):
            raise ValueError("malformed address: %r" % arg)
        addr = arg
    if " " in addr or addr.count("@") != 1:
        raise ValueError("malformed address: %r" % arg)
    local, domain = addr.split("@")
    if not local or not domain:
        raise ValueError("malformed address: %r" % arg)
    return addr


class SMTPServer(socketserver.ThreadingTCPServer):
    """Threaded TCP server holding the message store."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, maildir=None):
        super().__init__(address, SMTPHandler)
        self.messages = []
        self.lock = threading.Lock()
        self.maildir = maildir
        if maildir:
            os.makedirs(maildir, exist_ok=True)

    def store_message(self, message):
        with self.lock:
            self.messages.append(message)
            index = len(self.messages)
        if self.maildir:
            path = os.path.join(self.maildir, "%d.eml" % index)
            with open(path, "w", encoding="utf-8") as f:
                f.write("From: %s\n" % message.mail_from)
                for rcpt in message.rcpt_tos:
                    f.write("To: %s\n" % rcpt)
                f.write("\n")
                f.write(message.data)
                if not message.data.endswith("\n"):
                    f.write("\n")

    def get_messages(self):
        with self.lock:
            return list(self.messages)


class SMTPHandler(socketserver.StreamRequestHandler):
    """One SMTP session: greeting, then a command loop."""

    def handle(self):
        self.helo = False
        self.mail_from = None
        self.rcpt_tos = []
        self.wfile.write(
            ("220 %s %s\r\n" % (self.server.server_address[0] or "localhost", GREETING)).encode()
        )
        self.wfile.flush()
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            verb, _, rest = line.partition(" ")
            verb = verb.upper()
            if verb in ("HELO", "EHLO"):
                self._reply(*self._do_helo(rest))
            elif verb == "MAIL":
                self._reply(*self._do_mail(rest))
            elif verb == "RCPT":
                self._reply(*self._do_rcpt(rest))
            elif verb == "DATA":
                code, text = self._do_data(rest)
                self._reply(code, text)
            elif verb == "RSET":
                self.mail_from = None
                self.rcpt_tos = []
                self._reply(250, "OK")
            elif verb == "NOOP":
                self._reply(250, "OK")
            elif verb == "QUIT":
                self._reply(221, "Bye")
                return
            else:
                self._reply(500, "Command not recognized")

    def _reply(self, code, text):
        self.wfile.write(("%d %s\r\n" % (code, text)).encode())
        self.wfile.flush()

    def _do_helo(self, rest):
        if not rest.strip():
            return 501, "Syntax error: domain required"
        self.helo = True
        return 250, self.server.server_address[0] or "localhost"

    def _do_mail(self, rest):
        if not self.helo:
            return 503, "Bad sequence of commands: send HELO first"
        if not rest.upper().startswith("FROM:"):
            return 501, "Syntax error: expected MAIL FROM:<address>"
        try:
            addr = parse_address(rest[5:])
        except ValueError as exc:
            return 501, str(exc)
        self.mail_from = addr
        self.rcpt_tos = []
        return 250, "OK"

    def _do_rcpt(self, rest):
        if self.mail_from is None:
            return 503, "Bad sequence of commands: send MAIL first"
        if not rest.upper().startswith("TO:"):
            return 501, "Syntax error: expected RCPT TO:<address>"
        try:
            addr = parse_address(rest[3:])
        except ValueError as exc:
            return 501, str(exc)
        self.rcpt_tos.append(addr)
        return 250, "OK"

    def _do_data(self, rest):
        if rest.strip():
            return 501, "Syntax error: DATA takes no arguments"
        if self.mail_from is None or not self.rcpt_tos:
            return 503, "Bad sequence of commands: send MAIL and RCPT first"
        self._reply(354, "End data with <CR><LF>.<CR><LF>")
        lines = []
        while True:
            raw = self.rfile.readline()
            if not raw:
                return 451, "Connection closed during DATA"
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if line == ".":
                break
            if line.startswith(".."):
                line = line[1:]  # dot-unstuffing (RFC 5321 transparency)
            lines.append(line)
        message = Message(
            mail_from=self.mail_from,
            rcpt_tos=list(self.rcpt_tos),
            data="\n".join(lines) + ("\n" if lines else ""),
        )
        self.server.store_message(message)
        self.mail_from = None
        self.rcpt_tos = []
        return 250, "OK: message queued"

    # Note: _do_data replies 354 itself (before reading the body), so
    # handle() must not double-reply; it replies only the final code.


def main(argv=None):
    parser = argparse.ArgumentParser(description="Minimal SMTP server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2525)
    parser.add_argument("--maildir", default=None,
                        help="also store each message as <n>.eml here")
    args = parser.parse_args(argv)
    server = SMTPServer((args.host, args.port), maildir=args.maildir)
    host, port = server.server_address[:2]
    print("CC SMTP Server listening on %s:%d" % (host, port), flush=True)
    if args.maildir:
        print("Storing messages in %s" % args.maildir, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
