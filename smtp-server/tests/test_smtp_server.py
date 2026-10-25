"""Tests for smtp_server.py.

The real server runs in a background thread on an ephemeral loopback
port; tests speak raw SMTP and via stdlib smtplib. Nothing here ever
contacts a real mail server.
"""

import os
import smtplib
import socket
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtp_server import SMTPServer  # noqa: E402


class Session:
    """Tiny raw SMTP client over one socket."""

    def __init__(self, port):
        self.sock = socket.create_connection(("127.0.0.1", port))
        self.f = self.sock.makefile("rwb")
        self.greeting = self._read()

    def cmd(self, text):
        self.f.write((text + "\r\n").encode())
        self.f.flush()
        return self._read()

    def _read(self):
        return self.f.readline().decode("utf-8", errors="replace").strip()

    def data(self, lines):
        reply = self.cmd("DATA")
        assert reply.startswith("354"), reply
        for line in lines:
            self.f.write((line + "\r\n").encode())
        self.f.write(b".\r\n")
        self.f.flush()
        return self._read()

    def close(self):
        try:
            self.f.close()
            self.sock.close()
        except OSError:
            pass


class SMTPServerTestCase(unittest.TestCase):
    def setUp(self):
        self.maildir = tempfile.TemporaryDirectory()
        self.server = SMTPServer(("127.0.0.1", 0),
                                 maildir=self.maildir.name)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.sessions = []

    def tearDown(self):
        for s in self.sessions:
            s.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.maildir.cleanup()

    def session(self):
        s = Session(self.port)
        self.sessions.append(s)
        return s

    # --- greeting / initiation ---

    def test_greeting(self):
        s = self.session()
        self.assertTrue(s.greeting.startswith("220 "))
        self.assertIn("CC SMTP Server", s.greeting)

    def test_helo_and_ehlo(self):
        s = self.session()
        self.assertTrue(s.cmd("HELO client.example").startswith("250"))
        s2 = self.session()
        self.assertTrue(s2.cmd("EHLO client.example").startswith("250"))

    def test_helo_missing_argument(self):
        s = self.session()
        self.assertTrue(s.cmd("HELO").startswith("501"))

    def test_case_insensitivity(self):
        s = self.session()
        self.assertTrue(s.cmd("helo client.example").startswith("250"))
        self.assertTrue(
            s.cmd("mail from:<a@example.com>").startswith("250"))
        self.assertTrue(s.cmd("rcpt to:<b@example.com>").startswith("250"))
        reply = s.data(["Subject: hi", "", "body"])
        self.assertTrue(reply.startswith("250"))
        self.assertTrue(s.cmd("quit").startswith("221"))

    # --- sequencing / syntax errors ---

    def test_mail_before_helo_rejected(self):
        s = self.session()
        self.assertTrue(s.cmd("MAIL FROM:<a@example.com>").startswith("503"))

    def test_rcpt_before_mail_rejected(self):
        s = self.session()
        s.cmd("HELO client.example")
        self.assertTrue(s.cmd("RCPT TO:<b@example.com>").startswith("503"))

    def test_data_before_rcpt_rejected(self):
        s = self.session()
        s.cmd("HELO client.example")
        s.cmd("MAIL FROM:<a@example.com>")
        self.assertTrue(s.cmd("DATA").startswith("503"))

    def test_malformed_address_rejected(self):
        s = self.session()
        s.cmd("HELO client.example")
        self.assertTrue(s.cmd("MAIL FROM:<not-an-address>").startswith("501"))
        self.assertTrue(s.cmd("MAIL FROM:<a@>").startswith("501"))

    def test_noop_and_unknown_command(self):
        s = self.session()
        self.assertTrue(s.cmd("NOOP").startswith("250"))
        self.assertTrue(s.cmd("FROB x").startswith("500"))

    # --- full delivery ---

    def test_full_message_raw(self):
        s = self.session()
        s.cmd("HELO client.example")
        s.cmd("MAIL FROM:<alice@example.com>")
        s.cmd("RCPT TO:<bob@example.com>")
        s.cmd("RCPT TO:<carol@example.com>")
        reply = s.data(["Subject: hello", "", "first line",
                        "..dot-stuffed", "last"])
        self.assertTrue(reply.startswith("250"))
        msgs = self.server.get_messages()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].mail_from, "alice@example.com")
        self.assertEqual(msgs[0].rcpt_tos,
                         ["bob@example.com", "carol@example.com"])
        self.assertIn("Subject: hello", msgs[0].data)
        self.assertIn(".dot-stuffed", msgs[0].data)
        self.assertNotIn("..dot-stuffed", msgs[0].data)

    def test_null_reverse_path(self):
        s = self.session()
        s.cmd("HELO client.example")
        self.assertTrue(s.cmd("MAIL FROM:<>").startswith("250"))
        s.cmd("RCPT TO:<b@example.com>")
        self.assertTrue(s.data(["body"]).startswith("250"))
        self.assertEqual(self.server.get_messages()[0].mail_from, "")

    def test_second_message_same_connection(self):
        s = self.session()
        s.cmd("HELO client.example")
        for i in range(2):
            s.cmd("MAIL FROM:<a@example.com>")
            s.cmd("RCPT TO:<b@example.com>")
            self.assertTrue(s.data(["msg %d" % i]).startswith("250"))
        self.assertEqual(len(self.server.get_messages()), 2)

    def test_rset_clears_envelope(self):
        s = self.session()
        s.cmd("HELO client.example")
        s.cmd("MAIL FROM:<a@example.com>")
        s.cmd("RCPT TO:<b@example.com>")
        self.assertTrue(s.cmd("RSET").startswith("250"))
        self.assertTrue(s.cmd("DATA").startswith("503"))
        self.assertTrue(s.cmd("RCPT TO:<b@example.com>").startswith("503"))
        self.assertEqual(self.server.get_messages(), [])

    def test_quit(self):
        s = self.session()
        self.assertTrue(s.cmd("QUIT").startswith("221"))
        self.assertEqual(s.f.readline(), b"")

    # --- smtplib client ---

    def test_smtplib_sendmail(self):
        with smtplib.SMTP("127.0.0.1", self.port) as client:
            client.ehlo()
            client.sendmail("alice@example.com", ["bob@example.com"],
                            "Subject: via smtplib\r\n\r\nhello body")
        msgs = self.server.get_messages()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].mail_from, "alice@example.com")
        self.assertEqual(msgs[0].rcpt_tos, ["bob@example.com"])
        self.assertIn("Subject: via smtplib", msgs[0].data)
        self.assertIn("hello body", msgs[0].data)

    def test_concurrent_clients(self):
        def send(i):
            with smtplib.SMTP("127.0.0.1", self.port) as client:
                client.ehlo()
                client.sendmail("s%d@example.com" % i,
                                ["r@example.com"],
                                "Subject: %d\r\n\r\nbody %d" % (i, i))

        threads = [threading.Thread(target=send, args=(i,))
                   for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        msgs = self.server.get_messages()
        self.assertEqual(len(msgs), 5)
        self.assertEqual(
            sorted(m.mail_from for m in msgs),
            ["s%d@example.com" % i for i in range(5)])

    def test_maildir_storage(self):
        with smtplib.SMTP("127.0.0.1", self.port) as client:
            client.ehlo()
            client.sendmail("alice@example.com", ["bob@example.com"],
                            "Subject: filed\r\n\r\nfiled body")
        files = sorted(os.listdir(self.maildir.name))
        self.assertEqual(files, ["1.eml"])
        with open(os.path.join(self.maildir.name, files[0])) as f:
            content = f.read()
        self.assertIn("From: alice@example.com", content)
        self.assertIn("To: bob@example.com", content)
        self.assertIn("filed body", content)


if __name__ == "__main__":
    unittest.main()
