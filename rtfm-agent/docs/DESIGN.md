# RTFM For Me Agent — DESIGN

## Stack

Python 3 standard library only. One main file, `rtfm_agent.py`.
No third-party packages, no Redis server, no network calls in tests
(the HTTP server tests bind to an ephemeral localhost port and are
shut down in tearDown).

## Components (all in `rtfm_agent.py`)

### Chunking — `chunk_text(text, source, max_words=500, overlap_words=50)`

Paragraphs are split on blank lines; a line starting with `#` sets
the current section heading (it is a marker, not chunk content).
Paragraphs are accumulated until adding one would exceed
`max_words`; the chunk is then emitted and the next chunk starts
with the last `overlap_words` words of the previous chunk, so
boundary context survives. A new section heading also starts a new
chunk, so a chunk's section metadata always describes its content. A single over-long paragraph is split by
sentence, then by words if a sentence alone is still too long.
Each chunk is a dict: `text`, `source`, `section`, `position`
(0-based order in its document).

### Embeddings — `HashedEmbedding`

`EmbeddingProvider` is the interface (`embed(text) -> list[float]`).
`HashedEmbedding(dim=256)` lowercases, tokenises on word characters,
hashes each word with SHA-256 into a bucket, counts, and L2-normalises.
Deterministic, no model download, no API. Cosine similarity is then
plain keyword-overlap similarity — real retrieval over the local
text, with the limits disclosed in SPEC.md.

### Vector index — `DocumentStore`

In-memory stand-in for the challenge's Redis vector index. `ingest`
chunks a document, embeds each chunk, and deduplicates by
SHA-256 of `(source, chunk text)`: re-ingesting the same file adds
zero new chunks and reports the duplicate count. `search(query,
top_k=5, source=None, section=None)` embeds the query, scores every
chunk by cosine similarity, applies metadata filters first (the
hybrid-search behaviour), optionally boosts chunks whose section or
source matches a supplied memory topic, and returns
`(chunk, score)` pairs sorted by score, dropping zero-score chunks.

### Providers — `LLMProvider` / `FakeLLM` / `OpenAICompatibleLLM`

`LLMProvider.generate(prompt) -> str` is the pluggable interface.
`FakeLLM` (the test provider) parses the prompt's `Context:` blocks
(`[source#section] text`), scores each sentence by overlap with the
question's content words (stopwords removed), returns the top
sentences with a `Sources: <files>` citation line, and returns an
honest "I don't have enough information in the provided
documentation to answer that." when nothing overlaps. It knows no
fixture Q&A pairs; a new document with new wording works the same way.
`OpenAICompatibleLLM` posts stdlib-HTTP chat completions to a
configurable base URL with a model name and an API key read from a
named environment variable; it is NOT exercised against a live API
in this project (see SPEC.md).

### Semantic cache — `SemanticCache`

Stores `(question, embedding, answer)`. `lookup(question)` returns
the cached answer when the best cosine similarity is >= the
threshold (default 0.85, i.e. the challenge's 0.15 cosine distance);
otherwise it is a miss. `flush()` clears entries. Metrics counters
(hit/miss) live in `Metrics`, not in the cache itself.

### Sessions — `SessionStore`

`session_id -> [messages]` with an expiry timestamp per session.
Default TTL 24 hours (86 400 s, the challenge's suggestion);
configurable, including short TTLs for tests. Expired sessions read
back as empty and are pruned on access. `Agent` appends each
question/answer pair and includes recent messages in the prompt.

### Long-term memory — `MemoryStore`

Stores memories `{text, topics, entities}`. Extraction is
pattern-based: a message matching "I'm working on …", "I use …",
"I work on …", or "my project is …" yields a memory whose topics
are the message's content words and whose entities are its
capitalised / quoted phrases (best-effort heuristic, disclosed in
SPEC.md). `search(query)` ranks memories by word overlap.
`Agent.tell(text, session_id)` records a statement, extracts any
memory, and returns an acknowledgement; `Agent.ask` also extracts
from questions that carry such a statement.

### Agent — `Agent`

Owns a `DocumentStore`, a `SemanticCache` (optional), a
`SessionStore`, a `MemoryStore` (optional), an embedding provider,
an LLM provider, and `Metrics`. `ask(question, session_id=None,
source=None, section=None, top_k=5)`:

1. Tries the semantic cache (failures are caught and logged to
   stderr — graceful degradation, per Step 6).
2. Searches the document store (with metadata filters and a
   memory-topic boost from the user's stored memories).
3. Builds a prompt: system instruction (answer only from context,
   cite sources, say so if insufficient) + context blocks +
   session history + relevant memories + question.
4. Special case, disclosed: a question asking what the assistant
   knows about the user's project returns the stored memories
   directly, since an extractive fake provider cannot otherwise
   surface them.
5. Calls the LLM, stores the answer in the session and the cache,
   and returns `{answer, sources, cached, scores}` — `sources` are
   the files cited, extracted from the retrieved chunks.

`build_prompt(...)` is public so tests can assert that session
history and memories actually reach the prompt.

### Summarisation — `Agent.summarise_session(session_id)`

When a session's word count exceeds `summary_threshold_words`
(default 2 000), older messages are condensed to one summary line
("Earlier discussion covered: <topics>") and only the most recent
`keep_recent` messages are kept intact. This runs inside `ask`
before the prompt is built.

### Metrics — `Metrics`

Counters: cache hits/misses, LLM calls, ingest counts, plus total
latency for cached and uncached answers. `snapshot()` returns hit
rate, average cached/uncached latency, and `estimated_llm_calls_saved`
(= cache hits — each hit is one LLM call avoided). This mirrors the
challenge's `INCR`-based counters and `/metrics` endpoint without
claiming Redis persistence.

### REST API — `make_server(agent, host, port)`

`http.server.ThreadingHTTPServer` with a `BaseHTTPRequestHandler`:

- `POST /ingest` — `{"source": ..., "text": ...}` or
  `{"documents": [{"source": ..., "text": ...}]}`; returns chunks
  added / duplicates.
- `POST /ask` — `{"question": ..., "session_id": ...,
  "source": ..., "section": ...}`; returns the `ask()` result.
- `POST /ask/stream` — same body; replies with SSE-style `data:`
  lines carrying the answer word by word, then `data: [DONE]`.
- `GET /metrics` — the metrics snapshot.
- `POST /cache/flush` — clears the semantic cache.
- `GET /health` — `{"status": "ok"}`.

All responses are JSON except the stream. Unknown paths are 404,
malformed JSON / missing fields are 400. The server is started by
the CLI (`serve`) and by tests on port 0 (ephemeral).

### CLI

- `python3 rtfm_agent.py ingest <file>...` — ingest files from disk.
- `python3 rtfm_agent.py ask "question" [--session ID]
  [--source FILE] [--section SEC]` — print answer + sources.
- `python3 rtfm_agent.py serve [--port N] [--host H]` — start the API
  (default port 8000).
- `python3 rtfm_agent.py tell "statement" [--session ID]` — record
  context / long-term memory.

## Failure behaviour (Step 6)

Cache and memory are wrapped in try/except inside `ask`: a raising
cache or memory still yields a normal RAG answer (cache/metrics for
that call are simply not recorded). Only an empty document store
changes the answer — to the honest insufficient-information reply —
because vector search plus the LLM are the essential path.
