"""Tests for whois.py — local fake servers only, never real whois."""

import io
import socket
import socketserver
import sys
import threading
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

import whois


class FakeWhoisServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, response, received):
        self._response = response
        self.received = received
        super().__init__(("127.0.0.1", 0), self._Handler)

    class _Handler(socketserver.BaseRequestHandler):
        def handle(self):
            data = b""
            while not data.endswith(b"\n"):
                chunk = self.request.recv(4096)
                if not chunk:
                    break
                data += chunk
            self.server.received.append(data)
            # Send in two chunks to exercise read-until-EOF.
            payload = self.server._response.encode()
            half = len(payload) // 2
            self.request.sendall(payload[:half])
            self.request.sendall(payload[half:])


def start_fake(response):
    received = []
    server = FakeWhoisServer(response, received)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, received


class TestQuery(unittest.TestCase):
    def test_sends_crlf_and_reads_to_eof(self):
        server, received = start_fake("Domain Name: EXAMPLE.COM\n")
        try:
            text = whois.query("127.0.0.1", "example.com", port=server.server_address[1])
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(received, [b"example.com\r\n"])
        self.assertEqual(text, "Domain Name: EXAMPLE.COM\n")

    def test_refused_connection_raises(self):
        with self.assertRaises(OSError):
            whois.query("127.0.0.1", "example.com", port=1, timeout=2)


class TestParse(unittest.TestCase):
    def test_drops_blanks_and_comments(self):
        text = "% IANA WHOIS server\n\n% another comment\n  % indented\nDomain Name: EXAMPLE.COM\n"
        self.assertEqual(whois.parse_whois(text), {"domain name": ["EXAMPLE.COM"]})

    def test_first_colon_only_and_repeated_keys(self):
        text = ("Registrar URL: https://example.com:8080/x\n"
                "Name Server: NS1.EXAMPLE.COM\nName Server: NS2.EXAMPLE.COM\n")
        parsed = whois.parse_whois(text)
        self.assertEqual(parsed["registrar url"], ["https://example.com:8080/x"])
        self.assertEqual(parsed["name server"], ["NS1.EXAMPLE.COM", "NS2.EXAMPLE.COM"])

    def test_keys_lowercased(self):
        self.assertEqual(whois.parse_whois("DOMAIN NAME: X\n")["domain name"], ["X"])

    def test_colonless_continuation(self):
        text = "Registrant Street: 1601 Willow Rd\nSuite 100\n"
        self.assertEqual(whois.parse_whois(text)["registrant street"],
                         ["1601 Willow Rd Suite 100"])
        self.assertEqual(whois.parse_whois("orphan line\nDomain Name: X\n"),
                         {"domain name": ["X"]})


class TestReferral(unittest.TestCase):
    def test_refer_preferred_over_registrar(self):
        parsed = {"refer": ["whois.a.example"], "registrar whois server": ["whois.b.example"]}
        self.assertEqual(whois.find_referral(parsed), "whois.a.example")

    def test_registrar_fallback_and_none(self):
        self.assertEqual(
            whois.find_referral({"registrar whois server": ["whois.reg.example"]}),
            "whois.reg.example")
        self.assertIsNone(whois.find_referral({"domain name": ["X"]}))

    def test_strips_scheme_and_port(self):
        self.assertEqual(whois.find_referral({"refer": ["whois://whois.x.example:4343"]}),
                         "whois.x.example")


class TestLookup(unittest.TestCase):
    """Chain logic tested by stubbing query(); network behaviour is
    covered by TestQuery/TestMain against real fake servers."""

    def _chain(self, responses, **kwargs):
        calls = []
        def fake_query(server, query_text, port=43, timeout=10):
            calls.append((server, query_text))
            return responses[server]
        with unittest.mock.patch.object(whois, "query", side_effect=fake_query):
            hops = whois.lookup("example.com", server="whois.iana.org",
                                port=43, timeout=5, **kwargs)
        return hops, calls

    def test_two_hop_chain(self):
        responses = {
            "whois.iana.org": "refer: whois.verisign-grs.com\ndomain: COM\n",
            "whois.verisign-grs.com": "Domain Name: EXAMPLE.COM\n",
        }
        hops, calls = self._chain(responses)
        self.assertEqual([h[0] for h in hops],
                         ["whois.iana.org", "whois.verisign-grs.com"])
        self.assertEqual(calls, [("whois.iana.org", "example.com"),
                                 ("whois.verisign-grs.com", "example.com")])

    def test_registrar_hop_followed(self):
        responses = {
            "whois.verisign-grs.com": "Registrar WHOIS Server: whois.reg.example\n",
            "whois.reg.example": "Domain Name: EXAMPLE.COM\n",
        }
        with unittest.mock.patch.object(whois, "query",
                                        side_effect=lambda s, q, **kw: responses[s]):
            hops = whois.lookup("example.com", server="whois.verisign-grs.com")
        self.assertEqual(len(hops), 2)

    def test_no_follow_returns_one_hop(self):
        hops, _ = self._chain(
            {"whois.iana.org": "refer: whois.verisign-grs.com\n"},
            follow=False)
        self.assertEqual(len(hops), 1)

    def test_loop_terminates(self):
        hops, calls = self._chain({
            "whois.iana.org": "refer: whois.verisign-grs.com\n",
            "whois.verisign-grs.com": "refer: whois.iana.org\n",
        })
        self.assertEqual(len(hops), 2)
        self.assertEqual(len(calls), 2)

    def test_max_hops(self):
        responses = {
            "a.example": "refer: b.example\n",
            "b.example": "refer: c.example\n",
            "c.example": "Domain Name: X\n",
        }
        with unittest.mock.patch.object(whois, "query",
                                        side_effect=lambda s, q, **kw: responses[s]):
            hops = whois.lookup("example.com", server="a.example", max_hops=2)
        self.assertEqual(len(hops), 2)

    def test_lookup_refused_raises(self):
        with self.assertRaises(OSError):
            whois.lookup("example.com", server="127.0.0.1", port=1, timeout=2)


class TestMain(unittest.TestCase):
    def test_main_raw_and_parsed(self):
        server, _ = start_fake("% comment\n\nDomain Name: EXAMPLE.COM\n")
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                code = whois.main(["example.com", "--server", "127.0.0.1",
                                   "--port", str(server.server_address[1]),
                                   "--no-follow"])
            self.assertEqual(code, 0)
            self.assertIn("Domain Name: EXAMPLE.COM", out.getvalue())
            self.assertIn("% comment", out.getvalue())  # raw keeps comments

            out = io.StringIO()
            with redirect_stdout(out):
                code = whois.main(["example.com", "--server", "127.0.0.1",
                                   "--port", str(server.server_address[1]),
                                   "--no-follow", "--parsed"])
            self.assertEqual(code, 0)
            self.assertIn("domain name: EXAMPLE.COM", out.getvalue())
            self.assertNotIn("% comment", out.getvalue())
        finally:
            server.shutdown()
            server.server_close()

    def test_main_errors(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(whois.main([]), 2)
        with redirect_stderr(err):
            self.assertEqual(whois.main(["exa mple.com"]), 2)
        out = io.StringIO()
        with redirect_stderr(err):
            code = whois.main(["example.com", "--server", "127.0.0.1", "--port", "1"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
