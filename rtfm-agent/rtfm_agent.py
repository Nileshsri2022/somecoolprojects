#!/usr/bin/env python3
"""RTFM For Me Agent — RAG documentation assistant (stdlib only).

Implements Coding Challenge #110 (see docs/SPEC.md) with in-memory
stand-ins for the challenge's Redis Stack / RedisVL / Agent Memory
Server: document ingestion + chunking, hashed-vector retrieval,
answer-with-citations via a pluggable LLM provider, semantic caching,
session memory with TTL, pattern-based long-term memory, hybrid
(metadata-filtered) search, conversation summarisation, graceful
degradation, and a small REST API + CLI.

No real LLM or embedding API is called by default. Tests use
FakeLLM (generic extractive answerer) and HashedEmbedding only.
OpenAICompatibleLLM is provided for real use; it reads its API key
from a named environment variable and was not verified live here.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

INSUFFICIENT = (
    "I don't have enough information in the provided documentation "
    "to answer that."
)

STOPWORDS = set(
    "a an the is are was were be been being do does did how what "
    "why when where which who whom whose to of in on for with by "
    "at from as and or but if then than so such i you he she it "
    "we they this that these those my your his her its our their "
    "can could should would may might please tell me give show".split()
)

# ---------------------------------------------------------------- chunking


def _split_long_paragraph(text, section, max_words, overlap_words):
    """Split one over-long paragraph by sentence, then by words."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks, current = [], []
    for sentence in sentences:
        words = sentence.split()
        if not words:
            continue
        if len(current) + len(words) > max_words and current:
            chunks.append(" ".join(current))
            current = current[-overlap_words:] if overlap_words else []
        while len(words) > max_words:
            if current:
                chunks.append(" ".join(current))
                current = []
            chunks.append(" ".join(words[:max_words]))
            words = words[max_words - overlap_words:] if overlap_words else words[max_words:]
        current.extend(words)
    if current:
        chunks.append(" ".join(current))
    return [{"text": c, "section": section} for c in chunks]


def chunk_text(text, source, max_words=500, overlap_words=50):
    """Split text into overlapping chunks on paragraph boundaries.

    Returns a list of dicts: text, source, section, position.
    """
    # Collect (section, paragraph) pairs; headings set the section.
    items, section = [], ""
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if len(lines) == 1 and lines[0].lstrip().startswith("#"):
            section = lines[0].lstrip("#").strip()
            continue
        # A heading line at the top of a block still sets the section.
        if lines[0].lstrip().startswith("#"):
            section = lines[0].lstrip("#").strip()
            block = "\n".join(lines[1:]).strip()
            if not block:
                continue
        items.append((section, re.sub(r"\s+", " ", block)))

    chunks, current, current_section = [], [], ""
    for section, paragraph in items:
        words = paragraph.split()
        if len(words) > max_words:
            if current:
                chunks.append((" ".join(current), current_section))
                current = []
            chunks.extend(
                (c["text"], c["section"])
                for c in _split_long_paragraph(paragraph, section, max_words, overlap_words)
            )
            continue
        if current and len(current) + len(words) > max_words:
            chunks.append((" ".join(current), current_section))
            overlap = current[-overlap_words:] if overlap_words else []
            current = list(overlap)
            current_section = section
        if current and section != current_section:
            # A new section starts a new chunk: section metadata must
            # describe the chunk, not just its first paragraph.
            chunks.append((" ".join(current), current_section))
            current = []
        if not current:
            current_section = section
        current.extend(words)
    if current:
        chunks.append((" ".join(current), current_section))

    return [
        {"text": t, "source": source, "section": s, "position": i}
        for i, (t, s) in enumerate(chunks)
    ]


# ---------------------------------------------------------------- embeddings


def tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def content_words(text):
    return [w for w in tokenize(text) if w not in STOPWORDS]


class EmbeddingProvider:
    def embed(self, text):
        raise NotImplementedError


class HashedEmbedding(EmbeddingProvider):
    """Deterministic hashed bag-of-words embedding, L2-normalised."""

    def __init__(self, dim=256):
        self.dim = dim

    def embed(self, text):
        vec = [0.0] * self.dim
        for word in tokenize(text):
            bucket = int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.dim
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


# ---------------------------------------------------------------- providers


class LLMProvider:
    def generate(self, prompt):
        raise NotImplementedError


class FakeLLM(LLMProvider):
    """Generic extractive answerer for tests and offline use.

    Parses Context: blocks of the form ``[source#section] text`` from
    the prompt, scores sentences by content-word overlap with the
    question, and returns the best sentences with source citations.
    Knows no fixture questions or answers.
    """

    def __init__(self):
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        question = ""
        m = re.search(r"^Question:\s*(.*)$", prompt, re.MULTILINE)
        if m:
            question = m.group(1)
        qwords = set(content_words(question))
        context = ""
        m = re.search(r"Context:\n(.*?)\n\n(?:Conversation|Memories|Question:)",
                      prompt, re.DOTALL)
        if m:
            context = m.group(1)
        scored = []  # (score, sentence, source)
        for block in re.finditer(r"\[([^\]]+)\]\s*(.*?)(?=\n\[|\Z)", context, re.DOTALL):
            source = block.group(1).split("#")[0]
            for sentence in re.split(r"(?<=[.!?])\s+", block.group(2).strip()):
                sentence = sentence.strip()
                if not sentence:
                    continue
                score = len(set(content_words(sentence)) & qwords)
                if score:
                    scored.append((score, sentence, source))
        if not scored:
            return INSUFFICIENT
        scored.sort(key=lambda item: -item[0])
        seen, sentences, sources = set(), [], []
        for _, sentence, source in scored:
            if sentence not in seen:
                seen.add(sentence)
                sentences.append(sentence)
                if source not in sources:
                    sources.append(source)
            if len(sentences) >= 3:
                break
        return " ".join(sentences) + "\nSources: " + ", ".join(sources)


class OpenAICompatibleLLM(LLMProvider):
    """Chat-completions client over stdlib HTTP. NOT verified live.

    The API key is read from the named environment variable (default
    OPENAI_API_KEY) and is never hardcoded. Requires the user's own
    key and a reachable endpoint; untested in this project.
    """

    def __init__(self, model="gpt-4o-mini", base_url="https://api.openai.com/v1",
                 api_key_env="OPENAI_API_KEY"):
        self.model, self.base_url, self.api_key_env = model, base_url, api_key_env

    def generate(self, prompt):
        import urllib.request
        key = os.environ.get(self.api_key_env)
        if not key:
            raise RuntimeError(
                "No API key in environment variable %s; live LLM use "
                "needs the user's own key." % self.api_key_env)
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions", data=body,
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------- stores


class DocumentStore:
    """In-memory vector index: chunks + embeddings + metadata."""

    def __init__(self, embedding):
        self.embedding = embedding
        self.chunks = []          # dicts with text/source/section/position
        self.vectors = []         # parallel to chunks
        self._seen = set()        # sha256(source + text) for dedupe

    def ingest(self, source, text, max_words=500, overlap_words=50):
        added, duplicates = 0, 0
        for chunk in chunk_text(text, source, max_words, overlap_words):
            key = hashlib.sha256(
                (source + "\0" + chunk["text"]).encode()).hexdigest()
            if key in self._seen:
                duplicates += 1
                continue
            self._seen.add(key)
            self.chunks.append(chunk)
            self.vectors.append(self.embedding.embed(chunk["text"]))
            added += 1
        return {"added": added, "duplicates": duplicates}

    def search(self, query, top_k=5, source=None, section=None, boost_topics=()):
        qvec = self.embedding.embed(query)
        results = []
        for chunk, vec in zip(self.chunks, self.vectors):
            if source is not None and chunk["source"] != source:
                continue
            if section is not None and chunk["section"] != section:
                continue
            score = cosine(qvec, vec)
            if score <= 0:
                continue
            for topic in boost_topics:
                if topic.lower() in (chunk["section"] + " " + chunk["source"]).lower():
                    score *= 1.1
            results.append((chunk, score))
        results.sort(key=lambda item: -item[1])
        return results[:top_k]


class SemanticCache:
    """Semantic cache: question embedding -> answer, thresholded."""

    def __init__(self, embedding, threshold=0.85):
        self.embedding, self.threshold = embedding, threshold
        self.entries = []  # (question, vector, answer)

    def lookup(self, question):
        qvec = self.embedding.embed(question)
        best, best_score = None, 0.0
        for _, vec, answer in self.entries:
            score = cosine(qvec, vec)
            if score > best_score:
                best, best_score = answer, score
        if best is not None and best_score >= self.threshold:
            return best
        return None

    def store(self, question, answer):
        self.entries.append((question, self.embedding.embed(question), answer))

    def flush(self):
        self.entries.clear()


class SessionStore:
    """Session history with per-session TTL (default 24 hours)."""

    def __init__(self, ttl_seconds=86400):
        self.ttl = ttl_seconds
        self.sessions = {}  # id -> {"messages": [...], "expires": float}

    def _prune(self, session_id):
        entry = self.sessions.get(session_id)
        if entry and time.time() > entry["expires"]:
            del self.sessions[session_id]

    def append(self, session_id, role, text):
        self._prune(session_id)
        entry = self.sessions.setdefault(
            session_id, {"messages": [], "expires": time.time() + self.ttl})
        entry["messages"].append({"role": role, "text": text})
        entry["expires"] = time.time() + self.ttl

    def history(self, session_id):
        self._prune(session_id)
        entry = self.sessions.get(session_id)
        return list(entry["messages"]) if entry else []

    def summarise(self, session_id, threshold_words=2000, keep_recent=4):
        """Condense older messages once history exceeds the threshold."""
        entry = self.sessions.get(session_id)
        if not entry:
            return False
        total = sum(len(m["text"].split()) for m in entry["messages"])
        if total <= threshold_words or len(entry["messages"]) <= keep_recent:
            return False
        older, recent = entry["messages"][:-keep_recent], entry["messages"][-keep_recent:]
        topics = sorted({w for m in older for w in content_words(m["text"])})
        summary = {"role": "system",
                   "text": "Earlier discussion covered: " + ", ".join(topics[:20]) + "."}
        entry["messages"] = [summary] + recent
        return True


_MEMORY_PATTERNS = [
    re.compile(r"(?:i am|i'm)\s+working on\s+(.+)", re.IGNORECASE),
    re.compile(r"(?:i|we)\s+work on\s+(.+)", re.IGNORECASE),
    re.compile(r"my project is\s+(.+)", re.IGNORECASE),
    re.compile(r"i use\s+(.+)", re.IGNORECASE),
]


class MemoryStore:
    """Pattern-based long-term memory (stand-in for Memory Server)."""

    def __init__(self):
        self.memories = []  # {text, topics, entities}

    def extract(self, text):
        """Return a memory dict if the text states project context."""
        for pattern in _MEMORY_PATTERNS:
            m = pattern.search(text)
            if m:
                detail = m.group(1).strip().rstrip(".")
                entities = re.findall(r"[A-Z][A-Za-z0-9_-]+|\"([^\"]+)\"", text)
                entities = [e[0] if isinstance(e, tuple) else e
                            for e in entities]
                flat = [x for pair in
                        re.findall(r"[A-Z][A-Za-z0-9_-]+", text) for x in [pair]]
                return {"text": text.strip(), "topics": content_words(detail),
                        "entities": sorted(set(flat))}
        return None

    def add(self, text):
        memory = self.extract(text)
        if memory:
            self.memories.append(memory)
        return memory

    def search(self, query):
        qwords = set(content_words(query))
        scored = []
        for memory in self.memories:
            score = len(qwords & set(memory["topics"])) or \
                len(qwords & {w.lower() for w in memory["entities"]})
            if score:
                scored.append((score, memory))
        scored.sort(key=lambda item: -item[0])
        return [memory for _, memory in scored]


class Metrics:
    def __init__(self):
        self.hits = self.misses = self.llm_calls = 0
        self.cached_latency = self.uncached_latency = 0.0
        self.ingested = 0

    def snapshot(self):
        total = self.hits + self.misses
        return {
            "cache_hits": self.hits,
            "cache_misses": self.misses,
            "hit_rate": (self.hits / total) if total else 0.0,
            "avg_cached_latency_s": (self.cached_latency / self.hits) if self.hits else 0.0,
            "avg_uncached_latency_s": (self.uncached_latency / self.misses) if self.misses else 0.0,
            "estimated_llm_calls_saved": self.hits,
            "llm_calls": self.llm_calls,
            "chunks_ingested": self.ingested,
        }


# ---------------------------------------------------------------- agent


class Agent:
    SYSTEM_PROMPT = (
        "Answer using only the provided context and cite which source "
        "file each piece of information comes from. If the context does "
        "not contain enough information to answer the question, say so "
        "honestly rather than making something up."
    )

    def __init__(self, embedding=None, llm=None, cache=None,
                 sessions=None, memories=None):
        self.embedding = embedding or HashedEmbedding()
        self.llm = llm or FakeLLM()
        self.store = DocumentStore(self.embedding)
        self.cache = cache if cache is not None else SemanticCache(self.embedding)
        self.sessions = sessions or SessionStore()
        self.memories = memories if memories is not None else MemoryStore()
        self.metrics = Metrics()

    def build_prompt(self, question, retrieved, session_id=None):
        context = "\n".join(
            "[%s#%s] %s" % (c["source"], c["section"], c["text"])
            for c, _ in retrieved)
        history = ""
        if session_id:
            msgs = self.sessions.history(session_id)
            if msgs:
                history = "Conversation history:\n" + "\n".join(
                    "%s: %s" % (m["role"], m["text"]) for m in msgs) + "\n\n"
        memory_text = ""
        try:
            found = self.memories.search(question) if self.memories else []
        except Exception:
            found = []
        if found:
            memory_text = "Long-term memories:\n" + "\n".join(
                m["text"] for m in found) + "\n\n"
        return (
            self.SYSTEM_PROMPT + "\n\nContext:\n" + context + "\n\n"
            + history + memory_text + "Question: " + question)

    def ingest(self, source, text):
        result = self.store.ingest(source, text)
        self.metrics.ingested += result["added"]
        return result

    def tell(self, text, session_id="default"):
        if session_id:
            self.sessions.append(session_id, "user", text)
        memory = None
        try:
            memory = self.memories.add(text) if self.memories else None
        except Exception as exc:  # graceful degradation
            print("memory unavailable: %s" % exc, file=sys.stderr)
        if session_id:
            reply = "Noted."
            self.sessions.append(session_id, "assistant", reply)
            return reply
        return "Noted."

    def ask(self, question, session_id=None, source=None, section=None,
            top_k=5):
        started = time.time()
        # 1. Semantic cache (failure -> skip, never fail the ask).
        cached = None
        if self.cache is not None:
            try:
                cached = self.cache.lookup(question)
            except Exception as exc:
                print("cache unavailable: %s" % exc, file=sys.stderr)
                cached = None
        if cached is not None:
            self.metrics.hits += 1
            self.metrics.cached_latency += time.time() - started
            if session_id:
                self.sessions.append(session_id, "user", question)
                self.sessions.append(session_id, "assistant", cached)
            return {"answer": cached, "sources": [], "cached": True}
        self.metrics.misses += 1

        # 2. Memory-topic boost + hybrid (metadata-filtered) search.
        topics = []
        try:
            if self.memories:
                topics = [t for m in self.memories.search(question)
                          for t in m["topics"]]
        except Exception as exc:
            print("memory unavailable: %s" % exc, file=sys.stderr)
        retrieved = self.store.search(question, top_k=top_k, source=source,
                                      section=section, boost_topics=topics)
        sources = sorted({c["source"] for c, _ in retrieved})

        # 3. Memory-query shortcut (disclosed in SPEC.md).
        lowered = question.lower()
        if ("what do you know" in lowered or "my project" in lowered) \
                and self.memories:
            try:
                found = self.memories.search(question) or list(self.memories.memories)
            except Exception:
                found = []
            if found:
                answer = "From what you have told me: " + " ".join(
                    m["text"] for m in found)
                if session_id:
                    self.sessions.append(session_id, "user", question)
                    self.sessions.append(session_id, "assistant", answer)
                self.metrics.uncached_latency += time.time() - started
                return {"answer": answer, "sources": [], "cached": False}

        # 4. Summarise long sessions, then generate.
        if session_id:
            self.sessions.summarise(session_id)
            self.sessions.append(session_id, "user", question)
        prompt = self.build_prompt(question, retrieved, session_id)
        self.metrics.llm_calls += 1
        answer = self.llm.generate(prompt)
        if session_id:
            self.sessions.append(session_id, "assistant", answer)
        if self.cache is not None and answer != INSUFFICIENT:
            try:
                self.cache.store(question, answer)
            except Exception as exc:
                print("cache unavailable: %s" % exc, file=sys.stderr)
        # Memory extraction from statements carried in a question.
        try:
            if self.memories:
                self.memories.add(question)
        except Exception:
            pass
        self.metrics.uncached_latency += time.time() - started
        return {"answer": answer, "sources": sources, "cached": False}


# ---------------------------------------------------------------- REST API


def make_server(agent, host="127.0.0.1", port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output clean
            pass

        def _send(self, code, payload, content_type="application/json"):
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                return json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return None

        def do_GET(self):
            if self.path == "/health":
                self._send(200, {"status": "ok"})
            elif self.path == "/metrics":
                self._send(200, agent.metrics.snapshot())
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            data = self._read_json()
            if data is None:
                self._send(400, {"error": "malformed JSON"})
                return
            if self.path == "/ingest":
                docs = data.get("documents") or [
                    {"source": data.get("source"), "text": data.get("text")}]
                if any(not d.get("source") or d.get("text") is None for d in docs):
                    self._send(400, {"error": "source and text required"})
                    return
                total = {"added": 0, "duplicates": 0}
                for doc in docs:
                    result = agent.ingest(doc["source"], doc["text"])
                    total["added"] += result["added"]
                    total["duplicates"] += result["duplicates"]
                self._send(200, total)
            elif self.path == "/ask":
                if not data.get("question"):
                    self._send(400, {"error": "question required"})
                    return
                self._send(200, agent.ask(
                    data["question"], session_id=data.get("session_id"),
                    source=data.get("source"), section=data.get("section")))
            elif self.path == "/ask/stream":
                if not data.get("question"):
                    self._send(400, {"error": "question required"})
                    return
                result = agent.ask(data["question"],
                                   session_id=data.get("session_id"))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for word in result["answer"].split():
                    self.wfile.write(("data: %s\n\n" % word).encode())
                self.wfile.write(b"data: [DONE]\n\n")
            elif self.path == "/cache/flush":
                if agent.cache is not None:
                    agent.cache.flush()
                self._send(200, {"flushed": True})
            else:
                self._send(404, {"error": "not found"})

    return ThreadingHTTPServer((host, port), Handler)


# ---------------------------------------------------------------- CLI


def main(argv=None):
    parser = argparse.ArgumentParser(prog="rtfm_agent")
    sub = parser.add_subparsers(dest="command", required=True)
    ing = sub.add_parser("ingest")
    ing.add_argument("files", nargs="+")
    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--session", default=None)
    ask.add_argument("--source", default=None)
    ask.add_argument("--section", default=None)
    tell = sub.add_parser("tell")
    tell.add_argument("text")
    tell.add_argument("--session", default="default")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)

    agent = Agent()
    if args.command == "ingest":
        for path in args.files:
            if not os.path.exists(path):
                print("no such file: %s" % path, file=sys.stderr)
                return 1
            with open(path, encoding="utf-8") as fh:
                result = agent.ingest(os.path.basename(path), fh.read())
            print("%s: %s" % (path, result))
        return 0
    if args.command == "ask":
        result = agent.ask(args.question, session_id=args.session,
                           source=args.source, section=args.section)
        print(result["answer"])
        if result["sources"]:
            print("Sources: " + ", ".join(result["sources"]))
        return 0
    if args.command == "tell":
        print(agent.tell(args.text, session_id=args.session))
        return 0
    if args.command == "serve":
        server = make_server(agent, args.host, args.port)
        print("RTFM agent listening on %s:%d" % (args.host, server.server_address[1]))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
