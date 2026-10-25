"""Tests for the RTFM For Me Agent. Local fixtures + FakeLLM only."""

import json
import os
import subprocess
import sys
import threading
import time
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rtfm_agent import (  # noqa: E402
    INSUFFICIENT, Agent, DocumentStore, FakeLLM, HashedEmbedding,
    MemoryStore, SemanticCache, SessionStore, chunk_text, make_server,
)

API_DOC = """# API Reference

## Authentication

To authenticate, send your API key in the Authorization header.
To refresh the token, POST to /auth/refresh with your refresh token.

## Rate Limits

The API allows 100 requests per minute per API key.
"""

START_DOC = """# Getting Started

## Installation

Install the library with pip install widgetlib, then import widgetlib
in your Python code to get started quickly.

## Configuration

Set the WIDGET_API_KEY environment variable before running your code.
"""

AUTH_Q = "How do I authenticate to the API?"
INSTALL_Q = "How do I install the library?"


def make_agent():
    agent = Agent()
    agent.ingest("api-reference.md", API_DOC)
    agent.ingest("getting-started.md", START_DOC)
    return agent


class ChunkingTests(unittest.TestCase):
    def test_sections_and_positions(self):
        chunks = chunk_text(API_DOC, "api-reference.md")
        self.assertTrue(chunks)
        sections = [c["section"] for c in chunks]
        self.assertIn("Authentication", sections)
        self.assertIn("Rate Limits", sections)
        self.assertEqual([c["position"] for c in chunks],
                         list(range(len(chunks))))
        self.assertTrue(all(c["source"] == "api-reference.md" for c in chunks))

    def test_word_limit_and_overlap(self):
        text = " ".join("word%d" % i for i in range(100))
        chunks = chunk_text(text, "doc.md", max_words=20, overlap_words=5)
        self.assertTrue(all(len(c["text"].split()) <= 20 for c in chunks))
        self.assertGreater(len(chunks), 1)
        first_words = set(chunks[0]["text"].split())
        self.assertTrue(set(chunks[1]["text"].split()) & first_words)

    def test_long_paragraph_is_split_not_dropped(self):
        text = "Sentence one is here. " * 40
        chunks = chunk_text(text, "doc.md", max_words=20, overlap_words=0)
        joined = " ".join(c["text"] for c in chunks)
        self.assertIn("Sentence one is here.", joined)


class EmbeddingTests(unittest.TestCase):
    def test_deterministic_and_normalised(self):
        emb = HashedEmbedding()
        vec = emb.embed("hello world hello")
        self.assertEqual(vec, emb.embed("hello world hello"))
        self.assertAlmostEqual(sum(v * v for v in vec), 1.0, places=6)

    def test_empty_text_zero_vector(self):
        self.assertEqual(HashedEmbedding().embed(""), [0.0] * 256)


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.agent = make_agent()

    def test_auth_question_ranks_auth_chunk_first(self):
        results = self.agent.store.search(AUTH_Q)
        self.assertTrue(results)
        self.assertEqual(results[0][0]["section"], "Authentication")

    def test_source_filter(self):
        results = self.agent.store.search(
            "install widgetlib", source="getting-started.md")
        self.assertTrue(all(c["source"] == "getting-started.md"
                            for c, _ in results))

    def test_section_filter(self):
        results = self.agent.store.search(
            "API key", section="Rate Limits")
        self.assertTrue(all(c["section"] == "Rate Limits"
                            for c, _ in results))

    def test_no_match_returns_nothing(self):
        self.assertEqual(self.agent.store.search("zebra quantum flux"), [])

    def test_reingest_deduplicates(self):
        result = self.agent.ingest("api-reference.md", API_DOC)
        self.assertEqual(result["added"], 0)
        self.assertGreater(result["duplicates"], 0)


class AnswerTests(unittest.TestCase):
    def setUp(self):
        self.agent = make_agent()

    def test_covered_question_cites_correct_source(self):
        result = self.agent.ask(AUTH_Q)
        self.assertIn("Authorization header", result["answer"])
        self.assertIn("api-reference.md", result["answer"])
        self.assertIn("api-reference.md", result["sources"])

    def test_uncovered_question_is_honest(self):
        result = self.agent.ask("What is the pricing for enterprise plans?")
        self.assertEqual(result["answer"], INSUFFICIENT)
        self.assertNotIn("pricing", result["answer"].lower().replace(
            "information", ""))

    def test_multi_document_question_cites_both(self):
        result = self.agent.ask(
            "How do I install widgetlib and authenticate to the API?")
        self.assertIn("api-reference.md", result["sources"])
        self.assertIn("getting-started.md", result["sources"])

    def test_pluggable_counting_provider(self):
        class Counting(FakeLLM):
            pass
        agent = Agent(llm=Counting())
        agent.ingest("api-reference.md", API_DOC)
        agent.ask(AUTH_Q)
        self.assertEqual(agent.llm.calls, 1)
        agent.ask(AUTH_Q)  # cache hit: no new LLM call
        self.assertEqual(agent.llm.calls, 1)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.agent = make_agent()

    def test_repeat_ask_is_cached(self):
        first = self.agent.ask(AUTH_Q)
        self.assertFalse(first["cached"])
        second = self.agent.ask(AUTH_Q)
        self.assertTrue(second["cached"])
        self.assertEqual(second["answer"], first["answer"])
        self.assertEqual(self.agent.metrics.snapshot()["cache_hits"], 1)

    def test_slight_rephrase_hits(self):
        self.agent.ask(AUTH_Q)
        result = self.agent.ask("How do I authenticate to the API please?")
        self.assertTrue(result["cached"])

    def test_different_question_misses(self):
        self.agent.ask(AUTH_Q)
        result = self.agent.ask(INSTALL_Q)
        self.assertFalse(result["cached"])

    def test_flush_makes_cached_question_miss(self):
        self.agent.ask(AUTH_Q)
        self.agent.cache.flush()
        self.assertFalse(self.agent.ask(AUTH_Q)["cached"])

    def test_metrics_snapshot(self):
        self.agent.ask(AUTH_Q)
        self.agent.ask(AUTH_Q)
        snap = self.agent.metrics.snapshot()
        self.assertAlmostEqual(snap["hit_rate"], 0.5)
        self.assertEqual(snap["estimated_llm_calls_saved"], 1)
        self.assertGreaterEqual(snap["avg_uncached_latency_s"], 0.0)


class SessionTests(unittest.TestCase):
    def test_history_and_isolation(self):
        agent = make_agent()
        agent.ask(AUTH_Q, session_id="s1")
        agent.ask("How do I refresh the token?", session_id="s1")
        history = agent.sessions.history("s1")
        self.assertEqual(len(history), 4)  # 2 exchanges
        self.assertIn("refresh", history[-2]["text"])
        self.assertEqual(agent.sessions.history("s2"), [])

    def test_follow_up_retrieves_token_chunk(self):
        agent = make_agent()
        agent.ask(AUTH_Q, session_id="s1")
        result = agent.ask("How do I refresh the token?", session_id="s1")
        self.assertIn("/auth/refresh", result["answer"])

    def test_short_ttl_expires(self):
        store = SessionStore(ttl_seconds=0.05)
        store.append("s", "user", "hello")
        self.assertEqual(len(store.history("s")), 1)
        time.sleep(0.07)
        self.assertEqual(store.history("s"), [])

    def test_default_ttl_is_24_hours(self):
        self.assertEqual(SessionStore().ttl, 86400)


class MemoryTests(unittest.TestCase):
    def test_tell_stores_memory_for_new_session(self):
        agent = make_agent()
        agent.tell("I'm working on the payments microservice in Go",
                   session_id="s1")
        found = agent.memories.search("payments microservice")
        self.assertTrue(found)
        self.assertIn("payments", found[0]["text"])

    def test_prompt_includes_memory(self):
        agent = make_agent()
        agent.tell("I'm working on the payments microservice in Go",
                   session_id="s1")
        prompt = agent.build_prompt("How do I authenticate for the payments microservice?",
                                    agent.store.search("authenticate"),
                                    session_id="s2")
        self.assertIn("payments microservice", prompt)

    def test_what_do_you_know_surfaces_memory(self):
        agent = make_agent()
        agent.tell("I'm working on the payments microservice in Go",
                   session_id="s1")
        result = agent.ask("What do you know about my project?",
                           session_id="s2")
        self.assertIn("payments microservice", result["answer"])

    def test_unrelated_memory_search_empty(self):
        store = MemoryStore()
        store.add("I'm working on the payments microservice in Go")
        self.assertEqual(store.search("zebra quantum"), [])


class HybridAndSummaryTests(unittest.TestCase):
    def test_memory_topic_boosts_matching_section(self):
        store = DocumentStore(HashedEmbedding())
        store.ingest("a.md", "The token is required.")
        # Same sentence under two sections via two docs.
        store.ingest("b.md", "# Billing\n\nThe token is required.")
        boosted = store.search("token required", boost_topics=["billing"])
        plain = store.search("token required")
        self.assertNotEqual(boosted[0][0]["source"], plain[0][0]["source"])
        self.assertEqual(boosted[0][0]["source"], "b.md")

    def test_summarisation_keeps_recent(self):
        store = SessionStore()
        for i in range(10):
            store.append("s", "user", "message number %d about widgets" % i)
            store.append("s", "assistant", "reply number %d" % i)
        self.assertTrue(store.summarise("s", threshold_words=20,
                                        keep_recent=2))
        history = store.history("s")
        self.assertEqual(history[0]["role"], "system")
        self.assertIn("Earlier discussion", history[0]["text"])
        self.assertEqual(len(history), 3)


class DegradationTests(unittest.TestCase):
    def test_failing_cache_still_answers(self):
        class BrokenCache(SemanticCache):
            def lookup(self, q):
                raise RuntimeError("cache down")

            def store(self, q, a):
                raise RuntimeError("cache down")
        agent = Agent(cache=BrokenCache(HashedEmbedding()))
        agent.ingest("api-reference.md", API_DOC)
        result = agent.ask(AUTH_Q)
        self.assertIn("Authorization header", result["answer"])

    def test_failing_memory_still_answers(self):
        class BrokenMemory(MemoryStore):
            def search(self, q):
                raise RuntimeError("memory down")
        agent = Agent(memories=BrokenMemory())
        agent.ingest("api-reference.md", API_DOC)
        result = agent.ask(AUTH_Q)
        self.assertIn("Authorization header", result["answer"])


def _post(port, path, payload):
    req = urllib.request.Request(
        "http://127.0.0.1:%d%s" % (port, path),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read() or b"{}")


def _get(port, path):
    with urllib.request.urlopen(
            "http://127.0.0.1:%d%s" % (port, path), timeout=10) as resp:
        return resp.status, json.loads(resp.read() or b"{}")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.agent = make_agent()
        self.server = make_server(self.agent, port=0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_health_and_ingest_ask_flow(self):
        status, body = _get(self.port, "/health")
        self.assertEqual((status, body["status"]), (200, "ok"))
        status, body = _post(self.port, "/ingest",
                             {"source": "extra.md", "text": "# Notes\n\n"
                              "The widget colour is blue."})
        self.assertEqual(status, 200)
        self.assertGreater(body["added"], 0)
        status, body = _post(self.port, "/ask",
                             {"question": "What colour is the widget?"})
        self.assertEqual(status, 200)
        self.assertIn("blue", body["answer"])
        self.assertIn("extra.md", body["sources"])

    def test_metrics_and_flush_endpoints(self):
        _post(self.port, "/ask", {"question": AUTH_Q})
        _post(self.port, "/ask", {"question": AUTH_Q})
        _, snap = _get(self.port, "/metrics")
        self.assertEqual(snap["cache_hits"], 1)
        status, _ = _post(self.port, "/cache/flush", {})
        self.assertEqual(status, 200)
        _, body = _post(self.port, "/ask", {"question": AUTH_Q})
        self.assertFalse(body["cached"])

    def test_stream_endpoint(self):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/ask/stream" % self.port,
            data=json.dumps({"question": AUTH_Q}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
        self.assertIn("data:", body)
        self.assertIn("data: [DONE]", body)
        self.assertIn("Authorization", body)

    def test_bad_json_and_unknown_path(self):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/ask" % self.port, data=b"{not json",
            headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(
                "http://127.0.0.1:%d/nope" % self.port, timeout=10)
        self.assertEqual(ctx.exception.code, 404)


class CliTests(unittest.TestCase):
    def test_ingest_missing_file_exits_nonzero(self):
        proc = subprocess.run(
            [sys.executable, "rtfm_agent.py", "ingest", "/no/such/file.md"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)

    def test_ingest_file_succeeds(self):
        import tempfile
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "doc.md")
            with open(path, "w") as fh:
                fh.write("# Doc\n\nThe widget colour is blue.\n")
            proc = subprocess.run(
                [sys.executable, "rtfm_agent.py", "ingest", path],
                cwd=root, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("added", proc.stdout)


if __name__ == "__main__":
    unittest.main()
