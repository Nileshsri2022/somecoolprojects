"""Tests for llm-chatbot. Fake provider + local HTTP server only.

No test contacts a real LLM API or the internet. The HTTP
provider tests point at a throwaway server on an ephemeral
port (port 0) that is shut down in tearDown.
"""

import io
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chatbot import (  # noqa: E402
    ChatBot,
    Conversation,
    FakeProvider,
    HttpChatCompletionsProvider,
    run_chat,
)


class ConversationTests(unittest.TestCase):
    def test_system_prompt_is_first_message(self):
        conv = Conversation(system_prompt="Be brief.")
        conv.add_user("hi")
        self.assertEqual(conv.messages()[0], {"role": "system", "content": "Be brief."})

    def test_no_system_prompt_means_no_system_message(self):
        conv = Conversation()
        conv.add_user("hi")
        self.assertEqual(conv.messages(), [{"role": "user", "content": "hi"}])

    def test_turns_append_in_order_with_roles(self):
        conv = Conversation(system_prompt="S")
        conv.add_user("q1")
        conv.add_assistant("a1")
        conv.add_user("q2")
        self.assertEqual(
            [m["role"] for m in conv.messages()],
            ["system", "user", "assistant", "user"],
        )

    def test_empty_user_text_rejected(self):
        conv = Conversation()
        for bad in ("", "   "):
            with self.assertRaises(ValueError):
                conv.add_user(bad)

    def test_empty_assistant_text_rejected(self):
        conv = Conversation()
        with self.assertRaises(ValueError):
            conv.add_assistant("  ")

    def test_clear_drops_turns_keeps_system(self):
        conv = Conversation(system_prompt="S")
        conv.add_user("q")
        conv.clear()
        self.assertEqual(conv.messages(), [{"role": "system", "content": "S"}])

    def test_max_messages_keeps_system_drops_oldest_turns(self):
        conv = Conversation(system_prompt="S", max_messages=3)
        conv.add_user("q1")
        conv.add_assistant("a1")
        conv.add_user("q2")
        conv.add_assistant("a2")
        msgs = conv.messages()
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[-1], {"role": "assistant", "content": "a2"})

    def test_max_messages_fitting_only_system(self):
        conv = Conversation(system_prompt="S", max_messages=1)
        conv.add_user("q")
        self.assertEqual(conv.messages(), [{"role": "system", "content": "S"}])

    def test_no_cap_keeps_everything(self):
        conv = Conversation(max_messages=0)
        for i in range(20):
            conv.add_user(f"q{i}")
        self.assertEqual(len(conv.messages()), 20)

    def test_transcript_renders_role_lines(self):
        conv = Conversation(system_prompt="S")
        conv.add_user("hello")
        self.assertEqual(conv.transcript(), "system: S\nuser: hello")


class FakeProviderTests(unittest.TestCase):
    def test_complete_echoes_last_user_and_history_length(self):
        fake = FakeProvider()
        reply = fake.complete([
            {"role": "system", "content": "S"},
            {"role": "user", "content": "hello"},
        ])
        self.assertEqual(reply, "Fake reply (2 messages in history): hello")

    def test_complete_empty_messages_raises(self):
        with self.assertRaises(ValueError):
            FakeProvider().complete([])

    def test_stream_joins_to_complete_reply(self):
        fake = FakeProvider()
        messages = [{"role": "user", "content": "hello world"}]
        self.assertEqual("".join(fake.stream(messages)), fake.complete(messages))

    def test_seen_records_copy_not_live_reference(self):
        fake = FakeProvider()
        conv = Conversation(system_prompt="S")
        conv.add_user("q")
        fake.complete(conv.messages())
        conv.add_user("q2")  # must not rewrite the recorded copy
        self.assertEqual(len(fake.seen[0]), 2)


class ChatBotTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeProvider()
        self.bot = ChatBot(self.fake, Conversation(system_prompt="S"))

    def test_ask_stores_user_and_assistant_and_returns_reply(self):
        reply = self.bot.ask("hello")
        self.assertIn("hello", reply)
        roles = [m["role"] for m in self.bot.conversation.messages()]
        self.assertEqual(roles, ["system", "user", "assistant"])

    def test_second_ask_receives_first_turn_history(self):
        self.bot.ask("first")
        self.bot.ask("second")
        self.assertEqual(len(self.fake.seen[1]), 4)  # system + 2 turns + new user
        self.assertIn("second", self.fake.seen[1][-1]["content"])

    def test_ask_empty_stores_nothing(self):
        with self.assertRaises(ValueError):
            self.bot.ask("   ")
        self.assertEqual(self.bot.conversation.messages(),
                         [{"role": "system", "content": "S"}])

    def test_ask_failing_provider_stores_user_not_assistant(self):
        class Failing(FakeProvider):
            def complete(self, messages):
                raise RuntimeError("boom")
        bot = ChatBot(Failing(), Conversation(system_prompt="S"))
        with self.assertRaises(RuntimeError):
            bot.ask("hello")
        self.assertEqual([m["role"] for m in bot.conversation.messages()],
                         ["system", "user"])

    def test_ask_stream_stores_single_joined_assistant_turn(self):
        chunks = list(self.bot.ask_stream("hello"))
        self.assertEqual("".join(chunks), self.bot.conversation.messages()[-1]["content"])
        assistants = [m for m in self.bot.conversation.messages() if m["role"] == "assistant"]
        self.assertEqual(len(assistants), 1)

    def test_ask_stream_partial_failure_stores_partial_text(self):
        class Partial(FakeProvider):
            def stream(self, messages):
                yield "part-"
                raise RuntimeError("cut off")
        bot = ChatBot(Partial(), Conversation())
        with self.assertRaises(RuntimeError):
            list(bot.ask_stream("hello"))
        self.assertEqual(bot.conversation.messages()[-1],
                         {"role": "assistant", "content": "part-"})


def make_server(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


class HttpProviderTests(unittest.TestCase):
    def tearDown(self):
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server.server_close()

    def test_complete_posts_model_messages_and_auth(self):
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                captured["body"] = json.loads(self.rfile.read(length))
                captured["auth"] = self.headers.get("Authorization")
                payload = json.dumps(
                    {"choices": [{"message": {"content": "local answer"}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server, _ = make_server(Handler)
        port = self.server.server_address[1]
        provider = HttpChatCompletionsProvider(
            "test-key", model="test-model", base_url=f"http://127.0.0.1:{port}")
        reply = provider.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(reply, "local answer")
        self.assertEqual(captured["body"]["model"], "test-model")
        self.assertEqual(captured["body"]["messages"], [{"role": "user", "content": "hi"}])
        self.assertFalse(captured["body"]["stream"])
        self.assertEqual(captured["auth"], "Bearer test-key")

    def test_stream_parses_sse_and_ignores_done_and_blanks(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = (
                    b"\n"
                    b'data: {"choices": [{"delta": {"content": "hel"}}]}\n\n'
                    b'data: {"choices": [{"delta": {"content": "lo"}}]}\n\n'
                    b"data: [DONE]\n\n"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server, _ = make_server(Handler)
        port = self.server.server_address[1]
        provider = HttpChatCompletionsProvider(
            "k", base_url=f"http://127.0.0.1:{port}")
        self.assertEqual("".join(provider.stream([{"role": "user", "content": "hi"}])), "hello")

    def test_empty_key_rejected(self):
        with self.assertRaises(ValueError):
            HttpChatCompletionsProvider("")

    def test_http_error_raises_runtime_error_with_status(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = b"bad key"
                self.send_response(401)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server, _ = make_server(Handler)
        port = self.server.server_address[1]
        provider = HttpChatCompletionsProvider(
            "k", base_url=f"http://127.0.0.1:{port}")
        with self.assertRaisesRegex(RuntimeError, "401"):
            provider.complete([{"role": "user", "content": "hi"}])

    def test_malformed_json_raises_runtime_error(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = b"not json{"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server, _ = make_server(Handler)
        port = self.server.server_address[1]
        provider = HttpChatCompletionsProvider(
            "k", base_url=f"http://127.0.0.1:{port}")
        with self.assertRaises(RuntimeError):
            provider.complete([{"role": "user", "content": "hi"}])


class ChatLoopTests(unittest.TestCase):
    def run_loop(self, script, use_stream=True):
        fake = FakeProvider()
        bot = ChatBot(fake, Conversation(system_prompt="S"))
        out = io.StringIO()
        run_chat(bot, input_stream=io.StringIO(script), output_stream=out,
                 use_stream=use_stream)
        return fake, out.getvalue()

    def test_query_answered_and_exit_ends_session(self):
        fake, output = self.run_loop("hello\nexit\n", use_stream=False)
        self.assertIn("Your query: ", output)
        self.assertIn("Fake reply", output)
        self.assertEqual(len(fake.seen), 1)

    def test_quit_and_slash_exit_and_eof_end_session(self):
        for ending in ("quit\n", "/exit\n", ""):
            fake, _ = self.run_loop("hello\n" + ending, use_stream=False)
            self.assertEqual(len(fake.seen), 1)

    def test_empty_lines_ignored(self):
        fake, _ = self.run_loop("\n   \nhello\nexit\n", use_stream=False)
        self.assertEqual(len(fake.seen), 1)

    def test_history_command_does_not_call_provider(self):
        fake, output = self.run_loop("hello\n/history\nexit\n", use_stream=False)
        self.assertEqual(len(fake.seen), 1)
        self.assertIn("user: hello", output)

    def test_clear_resets_turns_keeps_system(self):
        fake, _ = self.run_loop("hello\n/clear\nworld\nexit\n", use_stream=False)
        # Second real query sees only system + itself.
        self.assertEqual(len(fake.seen[1]), 2)

    def test_help_lists_commands_without_calling_provider(self):
        fake, output = self.run_loop("/help\nexit\n", use_stream=False)
        self.assertEqual(len(fake.seen), 0)
        self.assertIn("/history", output)

    def test_streaming_mode_prints_chunks_then_newline(self):
        _, output = self.run_loop("hello\nexit\n", use_stream=True)
        # Reply is printed chunk-by-chunk, then a newline, then the next prompt.
        self.assertIn("Fake reply (2 messages in history): hello\nYour query: ", output)

    def test_provider_error_printed_and_loop_continues(self):
        class FailingOnce(FakeProvider):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def complete(self, messages):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("boom")
                return super().complete(messages)

        fake = FailingOnce()
        bot = ChatBot(fake, Conversation(system_prompt="S"))
        out = io.StringIO()
        run_chat(bot, input_stream=io.StringIO("first\nsecond\nexit\n"),
                 output_stream=out, use_stream=False)
        self.assertIn("Error: boom", out.getvalue())
        self.assertIn("Fake reply", out.getvalue())


if __name__ == "__main__":
    unittest.main()
