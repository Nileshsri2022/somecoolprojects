# RTFM For Me Agent — TEST_PLAN

Run: `python3 -m unittest discover -s tests -v` from
`rtfm-agent/`. Tests use local fixture documents written inline in
the test file and a local fake provider only — never a real LLM API,
never a network service except the ephemeral-port localhost HTTP
server tests (shut down in tearDown).

Fixture corpus (inline, two documents):

- `api-reference.md`: an Authentication section (API key in the
  `Authorization` header; refresh via `POST /auth/refresh` with a
  refresh token) and a Rate Limits section.
- `getting-started.md`: an Installation section (`pip install
  widgetlib`, then `import widgetlib`) and a Configuration section.

## Cases

### Chunking
- Paragraphs split on blank lines; section headings tracked per chunk.
- Chunk positions increase in document order.
- A long document chunks under the word limit with overlap words
  carried into the next chunk.
- A single over-long paragraph is split, not dropped.

### Embeddings and retrieval
- Embedding is deterministic and L2-normalised; empty text embeds
  to the zero vector.
- An authentication question ranks the Authentication chunk first.
- `source=` filter returns only that document; `section=` filter
  returns only that section; a filter matching nothing returns no
  chunks.

### Ingestion
- Ingesting a document stores its chunks with source/section/
  position metadata; re-ingesting the same document adds zero new
  chunks and counts duplicates.

### RAG answers (via `FakeLLM`, generic extractive provider)
- A directly covered question returns the documented fact and cites
  the correct source file.
- An uncovered question returns the honest insufficient-information
  reply and cites nothing it did not retrieve.
- A question spanning both documents cites both source files.
- A custom counting LLM provider is called exactly once per
  uncached ask and zero times for a cache hit (provider interface
  is genuinely pluggable).

### Semantic cache
- Asking the same question twice: second answer is cached, the LLM
  call count does not increase, metrics show a hit.
- A one-word-changed rephrase hits at the default threshold.
- A completely different question misses.
- `/metrics` (via `Metrics.snapshot`) shows hit rate and separate
  cached/uncached average latencies; hits count as saved LLM calls.
- Flushing the cache makes a previously cached question miss again.

### Sessions
- A follow-up question's session history contains the earlier
  exchange; a different session has no trace of it.
- A session with a short TTL reads back empty after expiry.
- Default TTL is 24 hours.

### Long-term memory
- `tell("I'm working on the payments microservice in Go")` stores
  a memory retrievable in a new session.
- `build_prompt` for a new session includes that stored memory.
- Asking what the assistant knows about the user's project surfaces
  the stored memory text.
- Memory search with an unrelated query returns nothing relevant.

### Hybrid search and summarisation
- A memory topic matching a section boosts that section's chunk
  above an otherwise equal chunk.
- A session past the word threshold summarises: older messages are
  replaced by a summary line and recent messages are kept.

### Graceful degradation
- An `ask` with a cache that raises on every call still returns a
  correct answer; likewise a memory store that raises on search.

### REST API (ephemeral port, killed in tearDown)
- `GET /health` returns ok.
- `POST /ingest` then `POST /ask` answers with a citation.
- `GET /metrics` reflects a prior ask; `POST /cache/flush` clears
  the cache (a repeat ask is uncached again).
- `POST /ask/stream` returns SSE-style `data:` lines containing
  answer words and a `[DONE]` terminator.
- Malformed JSON returns 400; an unknown path returns 404.

### CLI
- `ask` subcommand prints an answer for an ingested fixture via a
  temporary directory (library-level ingestion; the CLI itself holds
  no persistent store in this build — see README).
- `ingest` of a missing file exits non-zero.
