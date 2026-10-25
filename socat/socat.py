#!/usr/bin/env python3
"""socat clone (documented subset) — see README.md and docs/SPEC.md.

Establishes two bidirectional byte streams and transfers data between
them. Supported addresses: STDIO/STDIN/STDOUT, FILE/OPEN, TCP/TCP4/TCP6,
TCP-LISTEN/TCP4-LISTEN/TCP6-LISTEN, UDP/UDP4/UDP6, UDP-LISTEN/UDP4-LISTEN/
UDP6-LISTEN, EXEC. Python 3 standard library only.

NOT full socat: no SSL, proxy, UNIX sockets, raw sockets, PTY, or the
rest of socat's option catalogue. See docs/SPEC.md for the exact list.
"""

import os
import shlex
import signal
import socket
import subprocess
import sys
import threading

CHUNK = 65536
VERSION = "socat.py 1.0 (subset; see docs/SPEC.md)"

HELP = """\
Usage: socat [-u | -U] [-v] address1 address2
       socat -h | --help

Establishes two byte streams and transfers data between them
(bidirectional by default).

Options:
  -u            unidirectional: left address -> right address only
  -U            unidirectional: right address -> left address only
  -v            log connection/relay events to stderr
  -h, --help    show this help

Addresses (options are comma-separated after the address):
  -                     STDIO (same as STDIO)
  STDIO                 standard input / output
  STDIN                 standard input (read-only)
  STDOUT                standard output (write-only)
  FILE:path[,create|creat][,append][,trunc][,excl]
  OPEN:path[, ...]      same as FILE
  TCP:host:port         TCP client connection
  TCP4:host:port        TCP client, IPv4 only
  TCP6:host:port        TCP client, IPv6 only
  TCP-LISTEN:port[,reuseaddr][,fork][,bind=addr][,backlog=n]
  TCP4-LISTEN:port      TCP server, IPv4 only (same options)
  TCP6-LISTEN:port      TCP server, IPv6 only (same options)
  UDP:host:port         connected UDP socket
  UDP4:host:port        connected UDP, IPv4 only
  UDP6:host:port        connected UDP, IPv6 only
  UDP-LISTEN:port[,reuseaddr][,bind=addr]
  EXEC:'command'        run a command; stdout is read side, stdin is write side

Supported subset only: no SSL, proxy, UNIX sockets, raw sockets, PTY,
or other socat address types. EXEC commands are split with shlex and
run WITHOUT a shell, so pipes/redirects/globs inside the command are
not interpreted. See docs/SPEC.md for the full scope statement.
"""

VERBOSE = False


def log(msg):
    if VERBOSE:
        print(f"socat: {msg}", file=sys.stderr, flush=True)


class SocatError(Exception):
    pass


def split_options(spec):
    """Split an address spec on commas outside quotes.

    Returns (head, [options]) where head is the first token and options
    are the remaining tokens, each either 'name' or 'name=value'.
    """
    parts = []
    cur = []
    quote = None
    for ch in spec:
        if quote is not None:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            cur.append(ch)
        elif ch == ",":
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts[0], parts[1:]


def parse_options(tokens, allowed):
    """Parse option tokens against an allowed set.

    allowed: dict name -> True (flag) or False (needs =value).
    Returns dict name -> True or value string.
    """
    opts = {}
    for tok in tokens:
        if "=" in tok:
            name, value = tok.split("=", 1)
        else:
            name, value = tok, None
        if name not in allowed:
            raise SocatError(f"unknown option '{name}'")
        if allowed[name] and value is not None:
            raise SocatError(f"option '{name}' takes no value")
        if not allowed[name] and value is None:
            raise SocatError(f"option '{name}' requires a value")
        opts[name] = True if value is None else value
    return opts


def strip_quotes(s):
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


# ---------------------------------------------------------------- endpoints

class Endpoint:
    def read(self, n):
        raise NotImplementedError

    def write(self, data):
        raise NotImplementedError

    def shutdown_write(self):
        pass

    def close(self):
        pass


class StdioEndpoint(Endpoint):
    """fd 0 for reading, fd 1 for writing (raw fds, binary-safe)."""

    def __init__(self, read_ok=True, write_ok=True):
        self.read_ok = read_ok
        self.write_ok = write_ok

    def read(self, n):
        if not self.read_ok:
            return b""
        try:
            return os.read(0, n)
        except OSError:
            return b""

    def write(self, data):
        if not self.write_ok:
            raise SocatError("write to read-only STDIN endpoint")
        view = memoryview(data)
        while view:
            written = os.write(1, view)
            view = view[written:]

    def shutdown_write(self):
        pass  # cannot half-close stdout


class FileEndpoint(Endpoint):
    def __init__(self, path, opts):
        flags = os.O_RDWR
        if opts.get("create") or opts.get("creat"):
            flags |= os.O_CREAT
        if opts.get("excl"):
            if not (opts.get("create") or opts.get("creat")):
                raise SocatError("excl requires create")
            flags |= os.O_EXCL
        if opts.get("append"):
            flags |= os.O_APPEND
        if opts.get("trunc"):
            flags |= os.O_TRUNC
        if opts.get("append") and opts.get("trunc"):
            raise SocatError("append and trunc are mutually exclusive")
        try:
            self.fd = os.open(path, flags, 0o666)
        except FileNotFoundError:
            raise SocatError(f"file does not exist (use create): {path}")
        except FileExistsError:
            raise SocatError(f"file already exists (excl): {path}")
        except OSError as e:
            raise SocatError(f"cannot open file {path}: {e}")

    def read(self, n):
        try:
            return os.read(self.fd, n)
        except OSError:
            return b""

    def write(self, data):
        view = memoryview(data)
        while view:
            written = os.write(self.fd, view)
            view = view[written:]

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None


class SocketEndpoint(Endpoint):
    def __init__(self, sock):
        self.sock = sock

    def read(self, n):
        try:
            return self.sock.recv(n)
        except OSError:
            return b""

    def write(self, data):
        self.sock.sendall(data)

    def shutdown_write(self):
        try:
            self.sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class UdpListenEndpoint(Endpoint):
    """Bound UDP socket; first datagram fixes the peer."""

    def __init__(self, sock):
        self.sock = sock
        self.peer = None

    def read(self, n):
        try:
            data, addr = self.sock.recvfrom(min(n, 65535))
        except OSError:
            return b""
        if self.peer is None:
            self.peer = addr
            log(f"UDP peer fixed to {addr}")
        elif addr != self.peer:
            return self.read(n)  # drop other senders, wait for peer
        return data

    def write(self, data):
        if self.peer is None:
            raise SocatError("UDP-LISTEN: no peer yet, cannot send")
        self.sock.sendto(data, self.peer)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class ExecEndpoint(Endpoint):
    def __init__(self, command):
        argv = shlex.split(command)
        if not argv:
            raise SocatError("EXEC: empty command")
        try:
            self.proc = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE
            )
        except OSError as e:
            raise SocatError(f"EXEC: cannot run {argv[0]!r}: {e}")
        self._closed = False

    def read(self, n):
        try:
            return self.proc.stdout.read(n) or b""
        except (OSError, ValueError):
            return b""

    def write(self, data):
        try:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        except (OSError, ValueError, BrokenPipeError) as e:
            raise SocatError(f"EXEC: write failed: {e}")

    def shutdown_write(self):
        try:
            self.proc.stdin.close()
        except (OSError, ValueError):
            pass

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.proc.stdin.close()
        except (OSError, ValueError):
            pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        try:
            self.proc.stdout.close()
        except (OSError, ValueError):
            pass


# ---------------------------------------------------------------- parsing

FILE_OPTS = {
    "create": True, "creat": True, "append": True,
    "trunc": True, "excl": True,
}
LISTEN_OPTS = {
    "reuseaddr": True, "fork": True, "bind": False, "backlog": False,
}
CONNECT_OPTS = {"bind": False}
UDP_LISTEN_OPTS = {"reuseaddr": True, "bind": False}


def family_of(kind):
    if kind.endswith("4"):
        return socket.AF_INET
    if kind.endswith("6"):
        return socket.AF_INET6
    return None


def make_listener(head, opts):
    """Build a bound TCP listen socket from a LISTEN address."""
    kind, _, rest = head.partition(":")
    family = family_of(kind.replace("-LISTEN", ""))
    if not rest:
        raise SocatError(f"{kind}: missing port")
    if ":" in rest:  # host:port form
        host, _, port_s = rest.rpartition(":")
    else:
        host, port_s = opts.get("bind", ""), rest
    try:
        port = int(port_s)
    except ValueError:
        raise SocatError(f"{kind}: bad port {port_s!r}")
    if not 0 <= port <= 65535:
        raise SocatError(f"{kind}: port out of range: {port}")
    backlog = 5
    if "backlog" in opts:
        try:
            backlog = int(opts["backlog"])
        except ValueError:
            raise SocatError(f"bad backlog {opts['backlog']!r}")
    infos = socket.getaddrinfo(
        host or None, port,
        family or socket.AF_UNSPEC, socket.SOCK_STREAM,
        0, socket.AI_PASSIVE,
    )
    if not infos:
        raise SocatError(f"{kind}: cannot resolve listen address")
    last = None
    for af, socktype, proto, _canon, sockaddr in infos:
        try:
            s = socket.socket(af, socktype, proto)
            if opts.get("reuseaddr"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(sockaddr)
            s.listen(backlog)
            log(f"listening on {sockaddr}")
            return s
        except OSError as e:
            last = e
            try:
                s.close()
            except Exception:
                pass
    raise SocatError(f"{kind}: cannot listen: {last}")


def make_endpoint(spec):
    """Parse one address spec. Returns (endpoint, listen_info).

    listen_info is (socket, opts) for TCP-LISTEN addresses, else None.
    TCP-LISTEN endpoints are not opened here: the driver owns accept().
    """
    head, opt_tokens = split_options(spec)
    kind, _, rest = head.partition(":")
    kind_u = kind.upper()

    if kind_u in ("-", "STDIO"):
        if opt_tokens:
            raise SocatError(f"{kind}: STDIO takes no options")
        return StdioEndpoint(), None
    if kind_u == "STDIN":
        return StdioEndpoint(read_ok=True, write_ok=False), None
    if kind_u == "STDOUT":
        return StdioEndpoint(read_ok=False, write_ok=True), None

    if kind_u in ("FILE", "OPEN"):
        opts = parse_options(opt_tokens, FILE_OPTS)
        if not rest:
            raise SocatError(f"{kind}: missing path")
        return FileEndpoint(rest, opts), None

    if kind_u in ("TCP", "TCP4", "TCP6"):
        opts = parse_options(opt_tokens, CONNECT_OPTS)
        if rest.count(":") != 1:
            raise SocatError(f"{kind}: expected host:port, got {rest!r}")
        host, _, port_s = rest.rpartition(":")
        try:
            port = int(port_s)
        except ValueError:
            raise SocatError(f"{kind}: bad port {port_s!r}")
        fam = family_of(kind_u)
        try:
            sock = socket.create_connection(
                (host, port), timeout=30,
                source_address=(opts["bind"], 0) if "bind" in opts else None,
            )
        except OSError as e:
            raise SocatError(f"{kind}: cannot connect to {host}:{port}: {e}")
        if fam is not None and sock.family != fam:
            sock.close()
            raise SocatError(f"{kind}: resolved family does not match")
        log(f"connected to {host}:{port}")
        return SocketEndpoint(sock), None

    if kind_u in ("TCP-LISTEN", "TCP4-LISTEN", "TCP6-LISTEN"):
        opts = parse_options(opt_tokens, LISTEN_OPTS)
        listener = make_listener(head, opts)
        return None, (listener, opts)

    if kind_u in ("UDP", "UDP4", "UDP6"):
        opts = parse_options(opt_tokens, CONNECT_OPTS)
        if rest.count(":") != 1:
            raise SocatError(f"{kind}: expected host:port, got {rest!r}")
        host, _, port_s = rest.rpartition(":")
        try:
            port = int(port_s)
        except ValueError:
            raise SocatError(f"{kind}: bad port {port_s!r}")
        fam = family_of(kind_u)
        try:
            infos = socket.getaddrinfo(host, port, fam or socket.AF_UNSPEC,
                                       socket.SOCK_DGRAM)
            af, socktype, proto, _c, sockaddr = infos[0]
            sock = socket.socket(af, socktype, proto)
            if "bind" in opts:
                sock.bind((opts["bind"], 0))
            sock.connect(sockaddr)
        except OSError as e:
            raise SocatError(f"{kind}: cannot connect UDP {host}:{port}: {e}")
        log(f"UDP connected to {host}:{port}")
        return SocketEndpoint(sock), None

    if kind_u in ("UDP-LISTEN", "UDP4-LISTEN", "UDP6-LISTEN"):
        opts = parse_options(opt_tokens, UDP_LISTEN_OPTS)
        if not rest or ":" in rest:
            raise SocatError(f"{kind}: expected port, got {rest!r}")
        try:
            port = int(rest)
        except ValueError:
            raise SocatError(f"{kind}: bad port {rest!r}")
        fam = family_of(kind_u.replace("-LISTEN", ""))
        try:
            sock = socket.socket(fam or socket.AF_INET, socket.SOCK_DGRAM)
            if opts.get("reuseaddr"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((opts.get("bind", ""), port))
        except OSError as e:
            raise SocatError(f"{kind}: cannot bind UDP port {port}: {e}")
        log(f"UDP listening on port {port}")
        return UdpListenEndpoint(sock), None

    if kind_u == "EXEC":
        if opt_tokens:
            raise SocatError("EXEC: options are not supported; quote the command")
        if not rest:
            raise SocatError("EXEC: missing command")
        return ExecEndpoint(strip_quotes(rest)), None

    raise SocatError(
        f"unknown address type {kind!r} (supported: STDIO, FILE, OPEN, "
        "TCP, TCP-LISTEN, UDP, UDP-LISTEN, EXEC)"
    )


# ---------------------------------------------------------------- relay

def relay_one(src, dst):
    """Copy src -> dst until EOF; half-close dst on EOF. Returns error or None."""
    try:
        while True:
            data = src.read(CHUNK)
            if not data:
                break
            dst.write(data)
    except SocatError as e:
        return str(e)
    except OSError as e:
        return str(e)
    finally:
        try:
            dst.shutdown_write()
        except Exception:
            pass
    return None


def relay_bidirectional(left, right):
    errors = []

    def copy(src, dst):
        err = relay_one(src, dst)
        if err:
            errors.append(err)

    t1 = threading.Thread(target=copy, args=(left, right), daemon=True)
    t2 = threading.Thread(target=copy, args=(right, left), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    return errors[0] if errors else None


def run_once(left_factory, right_factory, unidir):
    """Open endpoints via factories and relay. Factories return endpoints."""
    left = left_factory()
    try:
        right = right_factory()
    except Exception:
        left.close()
        raise
    try:
        if unidir == "lr":
            err = relay_one(left, right)
        elif unidir == "rl":
            err = relay_one(right, left)
        else:
            err = relay_bidirectional(left, right)
        if err:
            raise SocatError(err)
    finally:
        left.close()
        right.close()


def main(argv):
    global VERBOSE
    args = []
    unidir = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(HELP)
            return 0
        elif a == "-u":
            if unidir is not None:
                print("socat: -u and -U are mutually exclusive", file=sys.stderr)
                return 1
            unidir = "lr"
        elif a == "-U":
            if unidir is not None:
                print("socat: -u and -U are mutually exclusive", file=sys.stderr)
                return 1
            unidir = "rl"
        elif a == "-v":
            VERBOSE = True
        elif a == "--version":
            print(VERSION)
            return 0
        elif a.startswith("-") and a != "-" and len(args) == 0 and not a[1:].isdigit():
            # Unknown flag (a lone "-" is STDIO; an address never starts with -)
            print(f"socat: unknown option {a}", file=sys.stderr)
            return 1
        else:
            args.append(a)
        i += 1
    if len(args) != 2:
        print("socat: exactly two addresses are required", file=sys.stderr)
        print(HELP, file=sys.stderr)
        return 1

    left_spec, right_spec = args

    # A listen address must be the left-hand side in this subset's driver
    # for fork mode; non-fork listen also works on the left. A listen
    # address on the right is rejected plainly rather than half-working.
    try:
        left, left_listen = make_endpoint(left_spec)
        if left_listen is not None:
            listener, listen_opts = left_listen
            if listen_opts.get("fork"):
                # Accept loop: fresh right endpoint per connection.
                def handler(conn):
                    try:
                        right = make_endpoint(right_spec)[0]
                        if right is None:
                            raise SocatError(
                                "listen address on both sides is not supported")
                        try:
                            if unidir == "lr":
                                err = relay_one(SocketEndpoint(conn), right)
                            elif unidir == "rl":
                                err = relay_one(right, SocketEndpoint(conn))
                            else:
                                err = relay_bidirectional(
                                    SocketEndpoint(conn), right)
                            if err:
                                print(f"socat: {err}", file=sys.stderr)
                        finally:
                            right.close()
                    except SocatError as e:
                        print(f"socat: {e}", file=sys.stderr)
                    finally:
                        try:
                            conn.close()
                        except OSError:
                            pass

                log("fork listener running (Ctrl-C to stop)")
                try:
                    while True:
                        conn, addr = listener.accept()
                        log(f"accepted connection from {addr}")
                        threading.Thread(
                            target=handler, args=(conn,), daemon=True).start()
                except KeyboardInterrupt:
                    return 130
                finally:
                    listener.close()
                return 0
            # Non-fork: accept exactly one connection, then relay.
            log("waiting for one connection")
            try:
                conn, addr = listener.accept()
            except KeyboardInterrupt:
                listener.close()
                return 130
            log(f"accepted connection from {addr}")
            listener.close()
            left = SocketEndpoint(conn)
            right, right_listen = make_endpoint(right_spec)
            if right_listen is not None:
                print("socat: listen address on both sides is not supported",
                      file=sys.stderr)
                left.close()
                right_listen[0].close()
                return 1
            try:
                if unidir == "lr":
                    err = relay_one(left, right)
                elif unidir == "rl":
                    err = relay_one(right, left)
                else:
                    err = relay_bidirectional(left, right)
                if err:
                    raise SocatError(err)
            finally:
                left.close()
                right.close()
            return 0
        right, right_listen = make_endpoint(right_spec)
        if right_listen is not None:
            print("socat: listen address must be the first address",
                  file=sys.stderr)
            left.close()
            right_listen[0].close()
            return 1
        try:
            if unidir == "lr":
                err = relay_one(left, right)
            elif unidir == "rl":
                err = relay_one(right, left)
            else:
                err = relay_bidirectional(left, right)
            if err:
                raise SocatError(err)
        finally:
            left.close()
            right.close()
        return 0
    except SocatError as e:
        print(f"socat: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    # SIGPIPE: writing to a closed pipe should surface as an error, not
    # kill the process silently mid-relay in a way tests can't see.
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
