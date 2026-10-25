#!/usr/bin/env python3
"""Minimal curl clone — HTTP/1.1 GET/DELETE/POST/PUT (+ HEAD/PATCH).

Build Your Own curl (codingchallenges.fyi, challenge-curl), Steps 1-6
plus Going Further #3 (HTTPS). Python 3 standard library only.

Usage: python3 curl.py [options] URL
  -v, --verbose            print > request / < response headers to stderr
  -i, --include            print response headers before the body on stdout
  -X, --request METHOD     HTTP method (default GET, or POST with -d)
  -d, --data DATA          request body (UTF-8); implies POST if no -X
  -H, --header "Name: V"   extra request header (repeatable)
  -o, --output FILE        write body to FILE instead of stdout
  -L, --location           follow redirects (301/302/303/307/308)
  --max-redirs N           redirect limit (default 10)
  -f, --fail               exit 22, no body, when final status >= 400
"""

import http.client
import socket
import ssl
import sys
import urllib.parse

DEFAULT_PORTS = {"http": 80, "https": 443}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRS_DEFAULT = 10


class CurlError(Exception):
    """An error with a curl-like exit code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class ParsedUrl:
    def __init__(self, scheme, host, port, target):
        self.scheme = scheme
        self.host = host
        self.port = port
        self.target = target

    @property
    def host_header(self):
        if self.port == DEFAULT_PORTS[self.scheme]:
            return self.host
        return "%s:%d" % (self.host, self.port)

    def __str__(self):
        return "%s://%s%s" % (self.scheme, self.host_header, self.target)


def parse_url(url):
    """Split a URL into scheme/host/port/target; fragment is dropped."""
    if not url:
        raise CurlError(3, "URL rejected: no URL given")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in DEFAULT_PORTS:
        if not parts.scheme:
            raise CurlError(3, "URL rejected: no scheme in %r" % url)
        raise CurlError(3, "URL rejected: unsupported scheme %r" % parts.scheme)
    if not parts.hostname:
        raise CurlError(3, "URL rejected: no host in %r" % url)
    try:
        port = parts.port
    except ValueError:
        raise CurlError(3, "URL rejected: invalid port in %r" % url)
    if port is None:
        port = DEFAULT_PORTS[parts.scheme]
    if not 1 <= port <= 65535:
        raise CurlError(3, "URL rejected: port out of range in %r" % url)
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    return ParsedUrl(parts.scheme, parts.hostname, port, target)


def parse_header(text):
    """Split one -H argument into (name, value); colon is required."""
    if ":" not in text:
        raise CurlError(3, "option -H: header %r has no colon" % text)
    name, value = text.split(":", 1)
    name = name.strip()
    value = value.strip()
    if not name:
        raise CurlError(3, "option -H: empty header name in %r" % text)
    return name, value


def build_headers(parsed, body, extra_headers):
    """Ordered request headers: built-ins, then -H (replacing on clash),
    then Content-Length if a body is present and not user-supplied."""
    headers = [
        ("Host", parsed.host_header),
        ("Accept", "*/*"),
        ("Connection", "close"),
    ]
    names = {name.lower() for name, _ in headers}
    for name, value in extra_headers:
        if name.lower() in names:
            headers = [(n, v) for n, v in headers if n.lower() != name.lower()]
        else:
            names.add(name.lower())
        headers.append((name, value))
    if body is not None and "content-length" not in {
        n.lower() for n, _ in headers
    }:
        headers.append(("Content-Length", str(len(body))))
    return headers


class Response:
    def __init__(self, status, reason, headers, body):
        self.status = status
        self.reason = reason
        self.headers = headers  # list of (name, value), order preserved
        self.body = body

    def header(self, name):
        name = name.lower()
        for key, value in self.headers:
            if key.lower() == name:
                return value
        return None


def _connection(parsed):
    if parsed.scheme == "https":
        context = ssl.create_default_context()
        return http.client.HTTPSConnection(
            parsed.host, parsed.port, timeout=30, context=context
        )
    return http.client.HTTPConnection(parsed.host, parsed.port, timeout=30)


def send_once(parsed, method, headers, body, verbose, err):
    """Send one request over a fresh Connection: close connection."""
    if verbose:
        err.write("> %s %s HTTP/1.1\n" % (method, parsed.target))
        for name, value in headers:
            err.write("> %s: %s\n" % (name, value))
        err.write(">\n")
    conn = _connection(parsed)
    try:
        # skip_host / skip_accept_encoding: http.client would otherwise
        # inject its own Host and Accept-Encoding headers; the wire
        # headers must be exactly the ones build_headers produced.
        conn.putrequest(method, parsed.target, skip_host=True,
                        skip_accept_encoding=True)
        for name, value in headers:
            conn.putheader(name, value)
        conn.endheaders(body)
        resp = conn.getresponse()
        data = resp.read()
    except socket.gaierror:
        raise CurlError(6, "Could not resolve host: %s" % parsed.host)
    except (ConnectionError, TimeoutError, ssl.SSLError, OSError) as exc:
        raise CurlError(7, "Failed to connect to %s: %s" % (parsed.host, exc))
    except http.client.HTTPException as exc:
        raise CurlError(7, "HTTP error talking to %s: %s" % (parsed.host, exc))
    finally:
        conn.close()
    if verbose:
        err.write("< HTTP/1.1 %d %s\n" % (resp.status, resp.reason))
        for name, value in resp.getheaders():
            err.write("< %s: %s\n" % (name, value))
        err.write("<\n")
    return Response(resp.status, resp.reason, resp.getheaders(), data)


def request(url, method=None, data=None, extra_headers=(),
            follow_redirects=False, max_redirs=MAX_REDIRS_DEFAULT,
            verbose=False, err=None):
    """Perform a request, following redirects iff asked. Returns Response."""
    err = err if err is not None else sys.stderr
    body = data.encode("utf-8") if isinstance(data, str) else data
    if method is None:
        method = "POST" if body is not None else "GET"
    method = method.upper()
    parsed = parse_url(url)
    hops = 0
    while True:
        headers = build_headers(parsed, body, extra_headers)
        resp = send_once(parsed, method, headers, body, verbose, err)
        location = resp.header("Location")
        if not (follow_redirects and resp.status in REDIRECT_STATUSES
                and location):
            return resp
        hops += 1
        if hops > max_redirs:
            raise CurlError(47, "Maximum (%d) redirects hit" % max_redirs)
        next_url = urllib.parse.urljoin(str(parsed), location)
        if resp.status == 303 and method != "HEAD":
            method, body = "GET", None
        elif resp.status in (301, 302) and method == "POST":
            method, body = "GET", None
        # 307/308 (and other methods on 301/302) keep method and body.
        parsed = parse_url(next_url)


USAGE = """Usage: curl.py [options] URL
  -v, --verbose            print request/response headers to stderr
  -i, --include            print response headers before the body
  -X, --request METHOD     HTTP method (default GET, or POST with -d)
  -d, --data DATA          request body; implies POST if no -X given
  -H, --header "Name: V"   extra request header (repeatable)
  -o, --output FILE        write body to FILE instead of stdout
  -L, --location           follow redirects
  --max-redirs N           redirect limit (default 10)
  -f, --fail               exit 22 when the final status is >= 400
"""


def parse_args(argv):
    """Hand-rolled parser (see DESIGN.md): curl-style errors and codes."""
    opts = {
        "verbose": False, "include": False, "method": None, "data": None,
        "headers": [], "output": None, "location": False,
        "max_redirs": MAX_REDIRS_DEFAULT, "fail": False,
    }
    url = None
    i = 0
    value_opts = {
        "-X": "method", "--request": "method",
        "-d": "data", "--data": "data",
        "-H": "headers", "--header": "headers",
        "-o": "output", "--output": "output",
        "--max-redirs": "max_redirs",
    }
    while i < len(argv):
        arg = argv[i]
        if arg in ("-v", "--verbose"):
            opts["verbose"] = True
        elif arg in ("-i", "--include"):
            opts["include"] = True
        elif arg in ("-L", "--location"):
            opts["location"] = True
        elif arg in ("-f", "--fail"):
            opts["fail"] = True
        elif arg in ("-h", "--help"):
            sys.stdout.write(USAGE)
            raise SystemExit(0)
        elif arg in value_opts:
            if i + 1 >= len(argv):
                raise CurlError(2, "option %s: requires a value" % arg)
            i += 1
            key = value_opts[arg]
            if key == "headers":
                opts["headers"].append(parse_header(argv[i]))
            elif key == "max_redirs":
                try:
                    opts["max_redirs"] = int(argv[i])
                except ValueError:
                    raise CurlError(3, "option --max-redirs: not a number: %r"
                                    % argv[i])
                if opts["max_redirs"] < 0:
                    raise CurlError(3, "option --max-redirs: negative")
            else:
                opts[key] = argv[i]
        elif arg.startswith("-") and arg != "-":
            raise CurlError(2, "option %s: unknown option" % arg)
        else:
            if url is not None:
                raise CurlError(2, "extra operand %r (only one URL allowed)"
                                % arg)
            url = arg
        i += 1
    if url is None:
        raise CurlError(2, "no URL given\n" + USAGE)
    return opts, url


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        opts, url = parse_args(argv)
        resp = request(
            url, method=opts["method"], data=opts["data"],
            extra_headers=opts["headers"],
            follow_redirects=opts["location"],
            max_redirs=opts["max_redirs"], verbose=opts["verbose"],
        )
    except CurlError as exc:
        sys.stderr.write("curl: (%d) %s\n" % (exc.code, exc.message))
        return exc.code
    except BrokenPipeError:
        return 23
    if opts["fail"] and resp.status >= 400:
        sys.stderr.write("curl: (22) The requested URL returned error: %d\n"
                         % resp.status)
        return 22
    out = sys.stdout.buffer
    outfile = None
    try:
        if opts["output"]:
            outfile = open(opts["output"], "wb")
            out = outfile
        if opts["include"]:
            out.write(("HTTP/1.1 %d %s\r\n" % (resp.status, resp.reason))
                      .encode("iso-8859-1"))
            for name, value in resp.headers:
                out.write(("%s: %s\r\n" % (name, value))
                          .encode("iso-8859-1"))
            out.write(b"\r\n")
        out.write(resp.body)
        out.flush()
    except OSError as exc:
        sys.stderr.write("curl: (23) Failure writing output: %s\n" % exc)
        return 23
    finally:
        if outfile is not None:
            outfile.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
