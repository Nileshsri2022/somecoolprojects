#!/usr/bin/env python3
"""ccnc — a minimal netcat clone (Coding Challenges: Build Your Own Netcat).

Python 3 standard library only. Supports the challenge page's steps:
TCP/UDP listen, TCP/UDP client, port scan (-z), execute (-e),
hex dump (-x), verbose (-v). See docs/SPEC.md.

Usage:
    python3 netcat.py -l -p 8888          # TCP listen
    python3 netcat.py -l -p 8888 -u       # UDP listen
    python3 netcat.py [-v] [-u] host port # client
    python3 netcat.py -z host 8880-8890   # port scan
    python3 netcat.py -l -p 8888 -e /bin/cat
    python3 netcat.py -x -l -p 8888       # hex dump (to stderr)
"""

import os
import socket
import subprocess
import sys
import threading

BUF = 4096


# ---------------------------------------------------------------- hex dump

def format_hexdump(data):
    """Format bytes the way the challenge page's Step 5 shows them.

    16 bytes per line, bytes grouped in fours, printable ASCII on
    the right ('.' otherwise). A short final line is padded so
    the ASCII column aligns with a full line's.
    """
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        groups = []
        for g in range(0, len(chunk), 4):
            groups.append(" ".join("%02X" % b for b in chunk[g:g + 4]))
        hex_field = "  ".join(groups).ljust(50)
        ascii_field = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append("%08X  %s  %s" % (off, hex_field, ascii_field))
    return lines


class Options:
    def __init__(self):
        self.listen = False
        self.udp = False
        self.verbose = False
        self.scan = False
        self.hexdump = False
        self.port = None          # int, from -p
        self.port_seen = False    # -p appeared (value may be deferred)
        self.execute = None
        self.host = None
        self.portspec = None      # client/scan port or range string


def _err(msg):
    print("netcat: %s" % msg, file=sys.stderr)


def parse_args(argv):
    """Hand-rolled parser: argparse cannot accept the page's Step 2
    ordering ``-l -p -u 8888`` (port after a later flag). Raises
    ValueError with a usage message on bad input."""
    opts = Options()
    positionals = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            positionals.extend(argv[i + 1:])
            break
        if len(arg) > 1 and arg.startswith("-") and not arg[1].isdigit():
            j = 1
            consumed_next = False
            while j < len(arg):
                ch = arg[j]
                if ch in "luvzx":
                    setattr(opts, {
                        "l": "listen", "u": "udp", "v": "verbose",
                        "z": "scan", "x": "hexdump"}[ch], True)
                    j += 1
                elif ch in "pe":
                    opts.port_seen = opts.port_seen or ch == "p"
                    rest = arg[j + 1:]
                    if rest:
                        value = rest
                    elif i + 1 < len(argv) and not (
                            argv[i + 1].startswith("-") and len(argv[i + 1]) > 1
                            and not argv[i + 1][1].isdigit()):
                        value = argv[i + 1]
                        consumed_next = True
                    else:
                        value = None  # deferred: filled from a positional
                    if ch == "p":
                        if value is not None:
                            try:
                                opts.port = int(value)
                            except ValueError:
                                raise ValueError("invalid port: %r" % value)
                    else:
                        if value is None:
                            raise ValueError("-e requires a program")
                        opts.execute = value
                    j = len(arg)
                else:
                    raise ValueError("unknown option: -%s" % ch)
            if consumed_next:
                i += 1
            i += 1
        else:
            positionals.append(arg)
            i += 1

    def is_number(s):
        try:
            int(s)
            return True
        except ValueError:
            return False

    if opts.listen:
        # Deferred -p, or a bare port positional, supplies the port.
        if opts.port is None:
            for pos in positionals:
                if is_number(pos):
                    opts.port = int(pos)
                    break
        if opts.port is None:
            raise ValueError("listen mode requires a port (-p PORT)")
        if not 1 <= opts.port <= 65535:
            raise ValueError("port out of range: %d" % opts.port)
    else:
        if len(positionals) < 1:
            raise ValueError("missing host")
        opts.host = positionals[0]
        if len(positionals) >= 2:
            opts.portspec = positionals[1]
        elif opts.port is not None:
            opts.portspec = str(opts.port)
        else:
            raise ValueError("missing port")
    return opts


def parse_ports(spec):
    """'8888' -> [8888]; '8880-8890' -> range list. Raises ValueError."""
    if "-" in spec:
        lo_s, hi_s = spec.split("-", 1)
        try:
            lo, hi = int(lo_s), int(hi_s)
        except ValueError:
            raise ValueError("invalid port range: %r" % spec)
        if not (1 <= lo <= hi <= 65535):
            raise ValueError("port range out of range: %r" % spec)
        return list(range(lo, hi + 1))
    try:
        port = int(spec)
    except ValueError:
        raise ValueError("invalid port: %r" % spec)
    if not 1 <= port <= 65535:
        raise ValueError("port out of range: %d" % port)
    return [port]


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def dump(data, direction, hexdump):
    if hexdump:
        log("%s %d bytes %s the socket" % (
            "Received" if direction == "in" else "Sent",
            len(data), "from" if direction == "in" else "to"))
        for line in format_hexdump(data):
            log(line)


# ---------------------------------------------------------------- pumps

def _stdin_to_socket(sock, udp_peer, hexdump):
    """stdin -> socket thread. On stdin EOF, shut down the TCP
    write side so the peer sees EOF; for UDP there is no EOF
    on the wire, so just stop sending.

    Uses os.read on fd 0, NOT sys.stdin.buffer: a daemon
    thread blocked in BufferedReader.read holds the reader
    lock at interpreter shutdown and Python aborts with
    SIGABRT ("could not acquire lock ... at interpreter
    shutdown"). Raw os.read has no such lock."""
    try:
        while True:
            data = os.read(0, BUF)
            if not data:
                break
            dump(data, "out", hexdump)
            if udp_peer is not None:
                # UDP listen: peer address supplied via shared list.
                while udp_peer[0] is None:
                    threading.Event().wait(0.05)
                sock.sendto(data, udp_peer[0])
            else:
                sock.sendall(data)
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        if udp_peer is None:
            try:
                sock.shutdown(socket.SHUT_WR)
            except OSError:
                pass


def _socket_to_stdout(sock, hexdump):
    """Main-thread loop: socket -> stdout until EOF (TCP)."""
    try:
        while True:
            data = sock.recv(BUF)
            if not data:
                break
            dump(data, "in", hexdump)
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
    except (ConnectionResetError, OSError):
        pass


def _udp_to_stdout(sock, udp_peer, hexdump):
    try:
        while True:
            data, addr = sock.recvfrom(BUF)
            udp_peer[0] = addr
            dump(data, "in", hexdump)
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
    except (ConnectionResetError, OSError):
        pass


def run_connected(sock, opts, udp_peer=None):
    """Bidirectional pump for an already-connected socket."""
    t = threading.Thread(target=_stdin_to_socket,
                         args=(sock, udp_peer, opts.hexdump), daemon=True)
    t.start()
    if udp_peer is not None:
        _udp_to_stdout(sock, udp_peer, opts.hexdump)
    else:
        _socket_to_stdout(sock, opts.hexdump)
    try:
        sock.close()
    except OSError:
        pass
    return 0


def run_execute(sock, opts):
    """-e: pipe a child process's stdin/stdout to/from the socket."""
    log("WARNING: -e gives unauthenticated remote execution to "
        "anyone who can connect; use only on localhost or a "
        "trusted network.")
    proc = subprocess.Popen([opts.execute], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def sock_to_proc():
        try:
            while True:
                data = sock.recv(BUF)
                if not data:
                    break
                dump(data, "in", opts.hexdump)
                proc.stdin.write(data)
                proc.stdin.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            try:
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

    t = threading.Thread(target=sock_to_proc, daemon=True)
    t.start()
    try:
        while True:
            data = proc.stdout.read1(BUF)
            if not data:
                break
            dump(data, "out", opts.hexdump)
            sock.sendall(data)
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        try:
            sock.close()
        except OSError:
            pass
        try:
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        proc.wait(timeout=5)
    return 0


# ---------------------------------------------------------------- modes

def run_listen(opts):
    proto = "udp" if opts.udp else "tcp"
    if opts.udp:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", opts.port))
        if opts.verbose:
            log("Listening on 0.0.0.0:%d [%s]" % (opts.port, proto))
        if opts.execute:
            # -e over UDP: wait for the first datagram, then treat
            # that peer as the connection (UDP has no accept()).
            # The first datagram is pre-fed to the child, then the
            # connected socket is pumped like the TCP case.
            log("WARNING: -e gives unauthenticated remote execution to "
                "anyone who can connect; use only on localhost or a "
                "trusted network.")
            data, addr = sock.recvfrom(BUF)
            connected = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            connected.connect(addr)
            if opts.hexdump:
                dump(data, "in", opts.hexdump)
            proc = subprocess.Popen(
                [opts.execute], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            proc.stdin.write(data)
            proc.stdin.flush()
            return _run_execute_udp(connected, proc, opts)
        peer = [None]
        return run_connected(sock, opts, udp_peer=peer)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", opts.port))
    sock.listen(1)
    if opts.verbose:
        log("Listening on 0.0.0.0:%d [%s]" % (opts.port, proto))
    conn, addr = sock.accept()
    if opts.verbose:
        log("Connection from %s:%d" % (addr[0], addr[1]))
    sock.close()
    if opts.execute:
        return run_execute(conn, opts)
    return run_connected(conn, opts)


def _run_execute_udp(sock, proc, opts):
    """UDP -e helper: child already received the first datagram."""
    def sock_to_proc():
        try:
            while True:
                data = sock.recv(BUF)
                if not data:
                    break
                dump(data, "in", opts.hexdump)
                proc.stdin.write(data)
                proc.stdin.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            try:
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

    t = threading.Thread(target=sock_to_proc, daemon=True)
    t.start()
    try:
        while True:
            data = proc.stdout.read1(BUF)
            if not data:
                break
            dump(data, "out", opts.hexdump)
            sock.sendall(data)
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        try:
            sock.close()
        except OSError:
            pass
        try:
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        proc.wait(timeout=5)
    return 0


def run_client(opts):
    ports = parse_ports(opts.portspec)
    if len(ports) != 1:
        raise ValueError("client mode takes a single port, not a range")
    port = ports[0]
    proto = "udp" if opts.udp else "tcp"
    if opts.udp:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((opts.host, port))
        if opts.verbose:
            log("Connection to %s port %d [%s] succeeded!"
                % (opts.host, port, proto))
        if opts.execute:
            return run_execute(sock, opts)
        return run_connected(sock, opts)
    try:
        sock = socket.create_connection((opts.host, port), timeout=10)
    except OSError as exc:
        _err("connect to %s port %d [%s] failed: %s"
             % (opts.host, port, proto, exc.strerror or exc))
        return 1
    if opts.verbose:
        log("Connection to %s port %d [%s] succeeded!"
            % (opts.host, port, proto))
    if opts.execute:
        return run_execute(sock, opts)
    return run_connected(sock, opts)


def run_scan(opts):
    ports = parse_ports(opts.portspec)
    proto = "udp" if opts.udp else "tcp"
    any_open = False
    for port in ports:
        try:
            if opts.udp:
                # No handshake exists: connect() alone cannot
                # prove a listener. Report the connect result
                # and let the caller know via the doc caveat.
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect((opts.host, port))
                s.close()
            else:
                s = socket.create_connection((opts.host, port), timeout=1)
                s.close()
            log("Connection to %s port %d [%s] succeeded!"
                % (opts.host, port, proto))
            any_open = True
        except OSError as exc:
            if opts.verbose:
                log("Connection to %s port %d [%s] failed: %s"
                    % (opts.host, port, proto, exc.strerror or exc))
    return 0 if any_open else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        opts = parse_args(argv)
    except ValueError as exc:
        _err(str(exc))
        _err("usage: netcat.py [-l] [-u] [-v] [-z] [-x] [-p PORT] "
             "[-e PROGRAM] [host] [port | lo-hi]")
        return 2
    try:
        if opts.scan:
            return run_scan(opts)
        if opts.listen:
            return run_listen(opts)
        return run_client(opts)
    except ValueError as exc:
        _err(str(exc))
        return 2
    except OSError as exc:
        _err(str(exc))
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
