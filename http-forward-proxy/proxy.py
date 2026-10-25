#!/usr/bin/env python3
"""HTTP forward proxy server (Coding Challenges #51).

Standard library only. See docs/SPEC.md and docs/DESIGN.md.

Usage:
    python3 proxy.py [--host 127.0.0.1] [--port 8989]
                     [--forbidden-hosts forbidden-hosts.txt]
                     [--banned-words banned-words.txt]
                     [--log-file proxy.log]

One HTTP request per client connection (Connection: close both
sides); CONNECT tunnels stay open until either side closes.
"""

import argparse
import os
import select
import socket
import socketserver
import sys
import threading
from datetime import datetime
from urllib.parse import urlparse

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-connection", "te", "trailer",
    "proxy-authorization", "proxy-authenticate", "upgrade",
}

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8989
BUFFER_SIZE = 65536
CONNECT_TIMEOUT = 10


# ---------------------------------------------------------------- lists

def load_list_file(path):
    """Load a one-item-per-line list, ignoring blanks and '#' comments.

    Returns lower-cased entries. ``None``, ``"none"`` or a missing
    file all yield an empty list.
    """
    if not path or path.lower() == "none":
        return []
    try:
        with open(path, encoding="utf-8") as f:
            entries = []
            for line in f:
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    entries.append(line)
            return entries
    except OSError:
        return []


def is_forbidden_host(host, forbidden_hosts):
    """Case-insensitive exact or subdomain match against the list."""
    host = (host or "").lower()
    for entry in forbidden_hosts:
        if host == entry or host.endswith("." + entry):
            return True
    return False


def contains_banned_word(body, banned_words):
    """Case-insensitive substring search over the raw body bytes."""
    if not banned_words or not body:
        return False
    lowered = body.lower()
    return any(word.encode("utf-8") for word in banned_words
               if word and word.encode("utf-8") in lowered)


def strip_hop_by_hop_headers(headers):
    """Drop hop-by-hop headers from a [(name, value), ...] list.

    Also drops any header named by the incoming ``Connection:``
    value, per RFC 7230 section 6.1.
    """
    named = set()
    for name, value in headers:
        if name.lower() == "connection":
            for token in value.split(","):
                named.add(token.strip().lower())
    return [(n, v) for (n, v) in headers
            if n.lower() not in HOP_BY_HOP and n.lower() not in named]


# ---------------------------------------------------------------- parsing

def _split_host_port(authority, default_port):
    """Split 'host' or 'host:port' (IPv6 '[::1]:port' included)."""
    authority = authority.strip()
    if authority.startswith("["):
        end = authority.find("]")
        if end == -1:
            raise ValueError("malformed host")
        host = authority[1:end]
        rest = authority[end + 1:]
        if rest.startswith(":"):
            return host, int(rest[1:])
        if rest:
            raise ValueError("malformed host")
        return host, default_port
    if ":" in authority:
        host, _, port = authority.rpartition(":")
        if not host or not port.isdigit():
            raise ValueError("malformed host")
        return host, int(port)
    if not authority:
        raise ValueError("missing host")
    return authority, default_port


def parse_request_target(method, target, host_header):
    """Return (host, port, origin_path) for a request.

    ``origin_path`` is None for CONNECT (authority-form target).
    Raises ValueError for https absolute-form, missing hosts and
    malformed targets — the proxy must not silently downgrade
    HTTPS to plain HTTP.
    """
    if method == "CONNECT":
        host, port = _split_host_port(target, 443)
        return host, port, None
    if target.startswith("http://") or target.startswith("https://"):
        parsed = urlparse(target)
        if parsed.scheme != "http":
            raise ValueError("https absolute-form requires CONNECT")
        if not parsed.hostname:
            raise ValueError("missing host")
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        return parsed.hostname, parsed.port or 80, path
    if target.startswith("/"):
        if not host_header:
            raise ValueError("missing Host header")
        host, port = _split_host_port(host_header, 80)
        return host, port, target
    raise ValueError("unsupported request target")


# ---------------------------------------------------------------- wire io

def read_headers(rfile):
    """Read header lines until the blank line; return [(name, value)]."""
    headers = []
    while True:
        line = rfile.readline(65536)
        if not line or line in (b"\r\n", b"\n"):
            break
        text = line.decode("iso-8859-1").rstrip("\r\n")
        if ":" not in text:
            continue
        name, _, value = text.partition(":")
        headers.append((name.strip(), value.strip()))
    return headers


def header_value(headers, name):
    for n, v in headers:
        if n.lower() == name.lower():
            return v
    return None


def _read_chunked(rfile):
    body = bytearray()
    while True:
        size_line = rfile.readline(65536).decode("iso-8859-1").strip()
        size = size_line.split(";", 1)[0]
        try:
            n = int(size, 16)
        except ValueError:
            break
        if n == 0:
            # Trailer headers up to the blank line; discarded.
            while True:
                line = rfile.readline(65536)
                if not line or line in (b"\r\n", b"\n"):
                    break
            break
        chunk = rfile.read(n)
        body.extend(chunk)
        rfile.readline(65536)  # trailing CRLF after the chunk
    return bytes(body)


def read_body(rfile, headers):
    """Read a body per Content-Length or chunked framing, else b''."""
    if header_value(headers, "Transfer-Encoding"):
        te = header_value(headers, "Transfer-Encoding").lower()
        if "chunked" in te:
            return _read_chunked(rfile)
    length = header_value(headers, "Content-Length")
    if length is not None:
        try:
            n = int(length)
        except ValueError:
            return b""
        if n <= 0:
            return b""
        return rfile.read(n)
    return b""


def read_response(rfile):
    """Read one origin response, skipping interim 1xx (e.g. 100).

    Returns (status_code, reason, headers, body)."""
    while True:
        status_line = rfile.readline(65536).decode("iso-8859-1").strip()
        if not status_line:
            raise ConnectionError("empty response from origin")
        parts = status_line.split(" ", 2)
        if len(parts) < 2:
            raise ConnectionError("malformed status line")
        try:
            code = int(parts[1])
        except ValueError:
            raise ConnectionError("malformed status code")
        reason = parts[2] if len(parts) > 2 else ""
        headers = read_headers(rfile)
        if 100 <= code < 200 and code != 101:
            continue  # interim response; the real one follows
        if (header_value(headers, "Transfer-Encoding") is None
                and header_value(headers, "Content-Length") is None):
            # Close-delimited body (HTTP/1.0 style): read until EOF.
            body = rfile.read()
        else:
            body = read_body(rfile, headers)
        return code, reason, headers, body


def _send_headers(sock, status_line, headers, body):
    out = [status_line.encode("iso-8859-1")]
    for name, value in headers:
        out.append(f"{name}: {value}".encode("iso-8859-1"))
    out.append(b"")
    out.append(b"")
    sock.sendall(b"\r\n".join(out))
    if body:
        sock.sendall(body)


def send_error(sock, code, reason, body_text):
    body = body_text.encode("utf-8")
    headers = [
        ("Content-Type", "text/plain; charset=utf-8"),
        ("X-Content-Type-Options", "nosniff"),
        ("Content-Length", str(len(body))),
        ("Connection", "close"),
    ]
    _send_headers(sock, f"HTTP/1.1 {code} {reason}", headers, body)


# ---------------------------------------------------------------- server

class ProxyServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, forbidden_hosts=(), banned_words=(),
                 log_file=None):
        self.forbidden_hosts = list(forbidden_hosts)
        self.banned_words = list(banned_words)
        self.log_file = log_file
        self._log_lock = threading.Lock()
        super().__init__(address, ProxyHandler)

    def log(self, message):
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
        print(line, flush=True)
        if self.log_file:
            with self._log_lock:
                try:
                    with open(self.log_file, "a", encoding="utf-8") as f:
                        f.write(line + "\n")
                except OSError:
                    pass


def create_proxy_server(host, port, forbidden_hosts=(), banned_words=(),
                        log_file=None):
    return ProxyServer((host, port), forbidden_hosts, banned_words, log_file)


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self._handle()
        except (ConnectionError, OSError, ValueError):
            pass  # client went away / bad socket; nothing to report

    def _handle(self):
        conn = self.request
        client = f"{self.client_address[0]}:{self.client_address[1]}"
        rfile = conn.makefile("rb")
        request_line = rfile.readline(65536).decode("iso-8859-1").strip()
        if not request_line:
            return
        parts = request_line.split()
        if len(parts) != 3:
            send_error(conn, 400, "Bad Request", "Bad Request")
            return
        method, target, _version = parts
        headers = read_headers(rfile)

        if method == "CONNECT":
            self._handle_connect(conn, client, target)
            return

        # 100-continue: answer now so the client sends its body.
        expect = header_value(headers, "Expect")
        if expect and expect.lower() == "100-continue":
            conn.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
        body = read_body(rfile, headers)

        try:
            host, port, path = parse_request_target(
                method, target, header_value(headers, "Host"))
        except ValueError:
            send_error(conn, 400, "Bad Request", "Bad Request")
            self.server.log(f"{client} {method} {target} 400")
            return

        if is_forbidden_host(host, self.server.forbidden_hosts):
            send_error(conn, 403, "Forbidden",
                       f"Website not allowed: {host}")
            self.server.log(f"{client} {method} {target} 403")
            return

        try:
            origin = socket.create_connection((host, port),
                                              timeout=CONNECT_TIMEOUT)
        except OSError:
            send_error(conn, 502, "Bad Gateway", "Bad Gateway")
            self.server.log(f"{client} {method} {target} 502")
            return
        try:
            forwarded = strip_hop_by_hop_headers(headers)
            forwarded = [(n, v) for (n, v) in forwarded
                         if n.lower() not in ("content-length",
                                              "transfer-encoding",
                                              "expect",
                                              "accept-encoding")]
            if header_value(headers, "Host") is None:
                forwarded.append(("Host", host if port == 80
                                  else f"{host}:{port}"))
            existing = header_value(forwarded, "X-Forwarded-For")
            xff = (existing + ", " + self.client_address[0]
                   if existing else self.client_address[0])
            forwarded = [(n, v) for (n, v) in forwarded
                         if n.lower() != "x-forwarded-for"]
            forwarded.append(("X-Forwarded-For", xff))
            forwarded.append(("Accept-Encoding", "identity"))
            forwarded.append(("Connection", "close"))
            if body or method in ("POST", "PUT", "PATCH"):
                forwarded.append(("Content-Length", str(len(body))))
            out = [f"{method} {path} HTTP/1.1".encode("iso-8859-1")]
            for name, value in forwarded:
                out.append(f"{name}: {value}".encode("iso-8859-1"))
            out.append(b"")
            out.append(b"")
            origin.sendall(b"\r\n".join(out))
            if body:
                origin.sendall(body)

            ofile = origin.makefile("rb")
            code, reason, resp_headers, resp_body = read_response(ofile)
            if method == "HEAD":
                resp_body = b""  # HEAD has no body, whatever CL says

            if method != "HEAD" and contains_banned_word(
                    resp_body, self.server.banned_words):
                send_error(conn, 403, "Forbidden",
                           "Website content not allowed.")
                self.server.log(f"{client} {method} {target} 403")
                return

            relayed = strip_hop_by_hop_headers(resp_headers)
            if method == "HEAD":
                relayed = [(n, v) for (n, v) in relayed
                           if n.lower() != "connection"]
                relayed.append(("Connection", "close"))
            else:
                relayed = [(n, v) for (n, v) in relayed
                           if n.lower() not in ("content-length",
                                                "transfer-encoding",
                                                "connection")]
                relayed.append(("Content-Length", str(len(resp_body))))
                relayed.append(("Connection", "close"))
            _send_headers(conn, f"HTTP/1.1 {code} {reason}",
                          relayed, resp_body)
            self.server.log(f"{client} {method} {target} {code}")
        finally:
            origin.close()

    def _handle_connect(self, conn, client, target):
        try:
            host, port, _ = parse_request_target("CONNECT", target, None)
        except ValueError:
            send_error(conn, 400, "Bad Request", "Bad Request")
            self.server.log(f"{client} CONNECT {target} 400")
            return
        if is_forbidden_host(host, self.server.forbidden_hosts):
            send_error(conn, 403, "Forbidden",
                       f"Website not allowed: {host}")
            self.server.log(f"{client} CONNECT {target} 403")
            return
        try:
            origin = socket.create_connection((host, port),
                                              timeout=CONNECT_TIMEOUT)
        except OSError:
            send_error(conn, 502, "Bad Gateway", "Bad Gateway")
            self.server.log(f"{client} CONNECT {target} 502")
            return
        try:
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self.server.log(f"{client} CONNECT {target} 200")
            self._tunnel(conn, origin)
        finally:
            origin.close()

    @staticmethod
    def _tunnel(a, b):
        """Copy bytes both ways until either side closes or errors."""
        sockets = [a, b]
        try:
            while True:
                readable, _, _ = select.select(sockets, [], [], 30)
                if not readable:
                    break
                for src in readable:
                    dst = b if src is a else a
                    try:
                        data = src.recv(BUFFER_SIZE)
                    except OSError:
                        return
                    if not data:
                        return
                    try:
                        dst.sendall(data)
                    except OSError:
                        return
        except (OSError, ValueError):
            pass


# ---------------------------------------------------------------- cli

def _resolve_list_arg(value, script_dir):
    if value is None or value.lower() == "none":
        return []
    if os.path.exists(value):
        return load_list_file(value)
    beside_script = os.path.join(script_dir, value)
    if os.path.exists(beside_script):
        return load_list_file(beside_script)
    print(f"warning: list file not found: {value} (using empty list)",
          file=sys.stderr)
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(description="HTTP forward proxy")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--forbidden-hosts", default="forbidden-hosts.txt")
    parser.add_argument("--banned-words", default="banned-words.txt")
    parser.add_argument("--log-file", default=None)
    args = parser.parse_args(argv)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    forbidden = _resolve_list_arg(args.forbidden_hosts, script_dir)
    banned = _resolve_list_arg(args.banned_words, script_dir)

    server = create_proxy_server(args.host, args.port, forbidden, banned,
                                 args.log_file)
    print(f"Starting proxy server on {args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
