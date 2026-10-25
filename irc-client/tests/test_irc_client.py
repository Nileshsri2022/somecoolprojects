"""Tests for irc_client.py. No public network, no fixed ports:
the fake server binds 127.0.0.1 port 0 (ephemeral)."""

import socket
import socketserver
import threading
import unittest

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from irc_client import IRCClient, Message, nick_of, parse_message


def make_client(**kwargs):
    shown = []
    client = IRCClient(nick="CCIRC", display=shown.append, **kwargs)
    return client, shown


class ParseTests(unittest.TestCase):
    def test_ping(self):
        self.assertEqual(parse_message("PING :token"),
                         Message(prefix=None, command="PING",
                                 params=["token"]))

    def test_welcome_numeric(self):
        msg = parse_message(
            ":*.freenode.net 002 CCIRC :Your host is *.freenode.net, "
            "running version InspIRCd-3")
        self.assertEqual(msg.prefix, "*.freenode.net")
        self.assertEqual(msg.command, "002")
        self.assertEqual(msg.params, ["CCIRC", "Your host is *.freenode.net, "
                                     "running version InspIRCd-3"])

    def test_notice(self):
        msg = parse_message(":*.freenode.net NOTICE * :* Looking up your ident...")
        self.assertEqual(msg.params, ["*", "* Looking up your ident..."])

    def test_step3_cases_verbatim(self):
        cases = [
            (":*.freenode.net 353 CCIRC = #cc :@CCIRC",
             Message("*.freenode.net", "353",
                     ["CCIRC", "=", "#cc", "@CCIRC"])),
            (":*.freenode.net NOTICE CCIRC :*** Ident lookup timed out, "
             "using ~guest instead.",
             Message("*.freenode.net", "NOTICE",
                     ["CCIRC", "*** Ident lookup timed out, "
                      "using ~guest instead."])),
            (":CCIRC!~guest@freenode-kge.qup.pic9tt.IP MODE CCIRC :+wRix",
             Message("CCIRC!~guest@freenode-kge.qup.pic9tt.IP", "MODE",
                     ["CCIRC", "+wRix"])),
            (":CCIRC!~guest@freenode-kge.qup.pic9tt.IP JOIN :#cc",
             Message("CCIRC!~guest@freenode-kge.qup.pic9tt.IP", "JOIN",
                     ["#cc"])),
            (":CCIRC!~guest@freenode-kge.qup.pic9tt.IP PART :#cc",
             Message("CCIRC!~guest@freenode-kge.qup.pic9tt.IP", "PART",
                     ["#cc"])),
            (":Guest4454!~guest@freenode-kge.qup.pic9tt.IP NICK :JohnC",
             Message("Guest4454!~guest@freenode-kge.qup.pic9tt.IP", "NICK",
                     ["JohnC"])),
        ]
        for line, expected in cases:
            with self.subTest(line=line):
                self.assertEqual(parse_message(line), expected)

    def test_privmsg_colons_in_text_kept_whole(self):
        msg = parse_message(":JohnC!~u@h PRIVMSG #cc :Hi: there: friend")
        self.assertEqual(msg.params, ["#cc", "Hi: there: friend"])

    def test_empty_line_ignored(self):
        self.assertIsNone(parse_message(""))
        self.assertIsNone(parse_message("\r\n"))

    def test_nick_of(self):
        self.assertEqual(nick_of("JohnC!~JohnC@host"), "JohnC")
        self.assertEqual(nick_of("some.server.net"), "some.server.net")
        self.assertEqual(nick_of(""), "")


class HandleLineTests(unittest.TestCase):
    def test_ping_returns_pong_and_displays_nothing(self):
        client, shown = make_client()
        self.assertEqual(client.handle_line("PING :abc"), ["PONG :abc"])
        self.assertEqual(shown, [])

    def test_own_join_sets_channel(self):
        client, shown = make_client()
        client.handle_line(":CCIRC!~guest@h JOIN :#cc")
        self.assertEqual(client.current_channel, "#cc")
        self.assertIn("You joined #cc", shown)

    def test_other_join_does_not_change_channel(self):
        client, shown = make_client()
        client.handle_line(":JohnC!~u@h JOIN :#cc")
        self.assertIsNone(client.current_channel)
        self.assertIn("JohnC joined #cc", shown)

    def test_own_part_clears_channel(self):
        client, shown = make_client()
        client.current_channel = "#cc"
        client.handle_line(":CCIRC!~guest@h PART :#cc")
        self.assertIsNone(client.current_channel)
        self.assertIn("You left #cc", shown)

    def test_other_part_with_reason(self):
        client, shown = make_client()
        client.handle_line(":JohnC!~u@h PART #cc :Goodbye")
        self.assertIn("JohnC left #cc (Goodbye)", shown)

    def test_own_nick_updates_nick(self):
        client, shown = make_client()
        client.handle_line(":CCIRC!~guest@h NICK :JohnC")
        self.assertEqual(client.nick, "JohnC")
        self.assertIn("CCIRC is now known as JohnC", shown)

    def test_other_nick_change(self):
        client, shown = make_client()
        client.handle_line(":JohnC!~u@h NICK :CCTest2")
        self.assertEqual(client.nick, "CCIRC")
        self.assertIn("JohnC is now known as CCTest2", shown)

    def test_privmsg_display(self):
        client, shown = make_client()
        client.handle_line(":JohnC!~u@h PRIVMSG #cc :Hi There!")
        self.assertIn("JohnC: Hi There!", shown)

    def test_private_privmsg_display(self):
        client, shown = make_client()
        client.handle_line(":JohnC!~u@h PRIVMSG CCIRC :hello privately")
        self.assertIn("JohnC: hello privately", shown)

    def test_quit_display(self):
        client, shown = make_client()
        client.handle_line(":JohnC!~u@h QUIT :Quit: Bye bye!")
        self.assertIn("JohnC has left IRC Quit: Bye bye!", shown)

    def test_names_display(self):
        client, shown = make_client()
        client.handle_line(":*.freenode.net 353 CCIRC = #cc :@CCIRC JohnC")
        self.assertIn("Users on #cc: @CCIRC JohnC", shown)

    def test_nick_in_use(self):
        client, shown = make_client()
        client.handle_line(":srv 433 * CCIRC :Nickname is already in use.")
        self.assertIn("Nickname CCIRC is already in use", shown)

    def test_partial_line_buffering(self):
        client, shown = make_client()
        self.assertEqual(client.feed_bytes(b"PING :to"), [])
        self.assertEqual(client.feed_bytes(b"ken\r\n"), ["PONG :token"])

    def test_auto_join_on_001(self):
        client, shown = make_client(channel="#cc")
        outgoing = client.handle_line(
            ":srv 001 CCIRC :Welcome to the network CCIRC")
        self.assertEqual(outgoing, ["JOIN #cc"])
        self.assertTrue(client.registered)
        self.assertIsNone(client.pending_channel)


class UserInputTests(unittest.TestCase):
    def test_join(self):
        client, _ = make_client()
        self.assertEqual(client.handle_user_input("/join #cc"),
                         (["JOIN #cc"], ""))

    def test_join_without_hash_rejected(self):
        client, _ = make_client()
        out, err = client.handle_user_input("/join cc")
        self.assertEqual(out, [])
        self.assertTrue(err)

    def test_part_with_and_without_channel(self):
        client, _ = make_client()
        self.assertEqual(client.handle_user_input("/part")[1] != "", True)
        client.current_channel = "#cc"
        self.assertEqual(client.handle_user_input("/part"),
                         (["PART #cc"], ""))

    def test_nick(self):
        client, _ = make_client()
        self.assertEqual(client.handle_user_input("/nick JohnC"),
                         (["NICK JohnC"], ""))

    def test_quit(self):
        client, _ = make_client()
        self.assertEqual(client.handle_user_input("/quit Bye bye!"),
                         (["QUIT :Bye bye!"], ""))
        self.assertEqual(client.handle_user_input("/quit"),
                         (["QUIT"], ""))

    def test_plain_text_needs_channel(self):
        client, _ = make_client()
        out, err = client.handle_user_input("hello")
        self.assertEqual(out, [])
        self.assertTrue(err)
        client.current_channel = "#cc"
        self.assertEqual(client.handle_user_input("hello"),
                         (["PRIVMSG #cc :hello"], ""))

    def test_unknown_command_and_empty(self):
        client, _ = make_client()
        out, err = client.handle_user_input("/bogus x")
        self.assertEqual(out, [])
        self.assertTrue(err)
        self.assertEqual(client.handle_user_input("   "), ([], ""))


# -- fake server ------------------------------------------------

class FakeIRCServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address):
        super().__init__(address, FakeHandler)
        self.received = []
        self.received_event = threading.Event()


class FakeHandler(socketserver.StreamRequestHandler):
    def handle(self):
        server = self.server
        # Registration.
        for _ in range(2):
            line = self.rfile.readline().decode("utf-8", "replace").strip()
            server.received.append(line)
        self.wfile.write(b":srv 001 CCIRC :Welcome to the test network CCIRC\r\n")
        self.wfile.write(b":srv 002 CCIRC :Your host is srv, running version test\r\n")
        self.wfile.write(b":srv NOTICE * :* Looking up your ident...\r\n")
        self.wfile.write(b"PING :tok123\r\n")
        self.wfile.flush()
        # Expect PONG, then JOIN.
        for _ in range(2):
            line = self.rfile.readline().decode("utf-8", "replace").strip()
            server.received.append(line)
        self.wfile.write(b":CCIRC!~guest@h JOIN :#cc\r\n")
        self.wfile.write(b":srv 353 CCIRC = #cc :@CCIRC JohnC\r\n")
        self.wfile.write(b":srv 366 CCIRC #cc :End of /NAMES list.\r\n")
        self.wfile.write(b":JohnC!~u@h PRIVMSG #cc :Hi There!\r\n")
        self.wfile.flush()
        # Expect PRIVMSG, then QUIT.
        for _ in range(2):
            line = self.rfile.readline().decode("utf-8", "replace").strip()
            server.received.append(line)
        server.received_event.set()


class IntegrationTests(unittest.TestCase):
    def test_full_session_against_fake_server(self):
        server = FakeIRCServer(("127.0.0.1", 0))
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            shown = []
            client = IRCClient(nick="CCIRC", host="127.0.0.1", port=port,
                               display=shown.append)
            client.connect()
            # Give the receiver thread time to answer PING.
            for _ in range(100):
                if len(server.received) >= 3:
                    break
                threading.Event().wait(0.05)
            self.assertEqual(server.received[:3],
                             ["NICK CCIRC",
                              "USER guest 0 * :Coding Challenges Client",
                              "PONG :tok123"])
            # The server now waits for JOIN; send it like /join would.
            client.send_line("JOIN #cc")
            # Server then sends JOIN echo + NAMES + a channel PRIVMSG.
            for _ in range(100):
                if "JohnC: Hi There!" in shown:
                    break
                threading.Event().wait(0.05)
            self.assertIn("JohnC: Hi There!", shown)
            self.assertEqual(client.current_channel, "#cc")
            client.send_line("PRIVMSG #cc :Hello back")
            client.send_line("QUIT :Bye bye!")
            self.assertTrue(server.received_event.wait(timeout=5))
            self.assertEqual(server.received[4:], ["PRIVMSG #cc :Hello back",
                                                   "QUIT :Bye bye!"])
        finally:
            client._stop.set()
            try:
                client._sock.close()
            except Exception:
                pass
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
