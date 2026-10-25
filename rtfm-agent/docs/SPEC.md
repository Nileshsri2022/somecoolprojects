# RTFM For Me Agent — SPEC

Coding Challenge #110, "Build Your Own RTFM For Me Agent"
(Coding Challenges / codingchallenges.fyi).

## Resolved challenge pages

- Site tag page (verified, read directly):
  <https://codingchallenges.fyi/challenges/tags/ai-agent> — lists exactly
  one doc under "AI Agent": "Build Your Own RTFM For Me Agent", described
  as an AI-powered documentation assistant that ingests technical
  documentation, answers questions about it using AI, and remembers
  context across conversations.
- Challenge text (verified, read directly, lines 0–202 of the post):
  <https://codingchallenges.substack.com/p/coding-challenge-110-rtfm-for-me>
  — Coding Challenge #110, the same challenge, in full-step form.
- Gap, stated honestly: a follow-on text fetch for the fyi detail page
  itself and for the tail of the Substack post (lines 202–263) was cut
  off by an upstream 429 rate limit, so the fyi detail-page URL is NOT
  claimed here and the final step's closing/testing lines were not
  re-read. Nothing below invents that tail: Step 6 is recorded from the
  portion that was read (lines 184–202), and its closing tests are
  marked "not re-read" rather than paraphrased as fact.

## What the challenge asks for

A full-stack AI assistant that ingests documentation files, answers
questions using retrieval-augmented generation (RAG), caches
semantically similar queries to reduce costs, and maintains memory
across sessions. Redis is the backbone in the challenge: vector search,
semantic caching, session storage, and long-term memory. The LLM,
embedding provider, language, and framework are the builder's choice.

### Step 0 — Environment and choices

- Run Redis Stack (Redis with built-in vector search) via
  `docker-compose.yml`.
- Choose an LLM and an embedding provider (OpenAI, Anthropic, Google
  Gemini, Mistral, Cohere, or local Ollama); note the embedding
  dimension, needed for the Redis vector index.
- Choose a programming language/framework (PydanticAI, LangChain,
  LlamaIndex, or direct API calls) and a Redis client library
  (RedisVL in Python/Java is suggested).
- Prepare sample documentation (markdown, text, or HTML); the Pro Git
  book (<https://github.com/progit/progit2>) is suggested as an example.
- Test: `redis-cli PING` returns `PONG`; verify the chosen LLM and
  embedding APIs can be called.

### Step 1 — Document ingestion pipeline

- Load sample documentation files.
- Split text into chunks of roughly 500 tokens each, with overlap
  between consecutive chunks so context is not lost at boundaries;
  split on natural boundaries (paragraphs) rather than mid-sentence.
- For each chunk, generate a vector embedding and store it in Redis
  with metadata: source file name, section heading, chunk position.
- Create a Redis vector index supporting similarity search over the
  embeddings, full-text search over chunk text, and filterable metadata
  (`FT.CREATE`).
- Test: `FT.INFO` shows the index and document count; `HGETALL` on a
  stored key shows chunk text, metadata, and embedding; re-ingesting
  the same files is handled sensibly (duplicates).

### Step 2 — Vector search and RAG answer generation

- Embed the user's question with the same model, search the vector
  index for the most similar chunks, and pass the top results to the
  LLM as context alongside the question.
- The system prompt instructs the LLM to answer using only the
  provided context and to cite which source file each piece of
  information comes from; if the context does not contain enough
  information, the LLM says so honestly instead of inventing an answer.
- Wrap this in a REST API with at least two endpoints: one for
  ingesting documents and one for asking questions. A streaming
  endpoint (server-sent events) is a nice addition.
- Test: a directly-covered question is answered accurately with the
  correct source citation and no out-of-doc information; an uncovered
  question gets an honest "not enough information" answer; a question
  spanning multiple documents pulls context from several sources;
  verify the endpoints with `curl`.

### Step 3 — Semantic caching

- Cache by meaning, not exact string: embed the question and check
  whether a previously cached question is close enough in vector
  space; if so, serve the cached answer with no LLM call.
- A separate Redis vector index for cache entries stores the original
  question, its embedding, and the generated response.
- Start with a similarity threshold of around 0.15 (cosine distance)
  and tune: too strict rarely hits, too loose serves wrong answers.
  (RedisVL `SemanticCache` / `LangCache` are suggested for Python.)
- Track cache metrics — hit rate, average latency for cached versus
  uncached responses, estimated cost savings — stored with `INCR` so
  they persist across restarts, and exposed through a `/metrics`
  endpoint.
- Test: asking twice is faster the second time and shows a cache hit;
  a slight rephrase also hits if the threshold is tuned; a completely
  different question misses; `/metrics` shows hit rate and latency
  comparison; a cache-flush endpoint makes previously cached queries
  miss again.

### Step 4 — Session memory

- Store conversation messages in Redis, keyed by session ID (lists or
  streams); include recent messages in the LLM prompt so follow-up
  questions ("how do I refresh the token?" after an authentication
  question) resolve against earlier context.
- Set a time-to-live on sessions so they clean up automatically after
  inactivity — 24 hours is the suggested default.
- Test: a follow-up relying on earlier context is understood; a
  different session has no memory of the first; after the TTL expires
  (or a short TTL for testing) the session data is cleaned up.

### Step 5 — Long-term agent memory

- Run the Redis Agent Memory Server as a Docker container alongside
  Redis; it provides a REST API for storing/searching memories with
  topic extraction, entity recognition, and semantic search, and
  supports 100+ LLM providers via LiteLLM.
- After each conversation, extract important context (user
  preferences, project details, technical decisions) and store it as
  long-term memory; before generating answers, search for relevant
  memories and include them in the prompt.
- The prompt then assembles three sources: document chunks from
  vector search, recent session messages, and relevant long-term
  memories (e.g. a user who mentioned Python gets Python-leaning
  examples where possible).
- Test: context told in one session ("I'm building a payment service
  in Go") shapes answers in a new session; the memory server's REST
  API shows memories stored with correct topics/entities; asking the
  assistant what it knows surfaces the stored memories.

### Step 6 — Hybrid search and production hardening

- Hybrid search combines vector similarity with metadata filtering:
  e.g. "how does authentication work in the API reference?" finds
  semantically relevant chunks and narrows them to the API reference
  document. Long-term memory context can also apply filters
  automatically (e.g. prioritise authentication-related sections).
- Conversation summarisation: when history grows beyond a token
  threshold, summarise older messages and keep only recent ones
  intact, so the context window does not overflow while earlier
  information is preserved.
- Graceful degradation: if the semantic cache is unavailable, skip it
  and call the LLM directly; if the memory server is down, answer
  without long-term context. Only vector search and the LLM are truly
  essential — everything else fails silently with appropriate logging.
- Testing tail for this step: NOT re-read (see "Gap" above); the
  behaviour is implemented and tested here on the same pattern as the
  earlier steps (filtered search, summarisation, degradation), and
  this gap is disclosed rather than filled with invented test text.

## Deliberate divergences (all in the code, none silent)

1. No Redis, no Docker, no live LLM. The challenge's Redis Stack,
   RedisVL, and Agent Memory Server are replaced by in-memory
   equivalents with the same interfaces and semantics (vector index,
   semantic-cache index, session store with TTL, memory store). This
   keeps the build runnable with Python 3 standard library only and
   is the reason live `PING`/`FT.INFO`/`HGETALL` checks are NOT
   claimed. A `docker-compose.yml` for Redis Stack is therefore not
   shipped: shipping one that was never run would be a fake artefact.
2. Embeddings are a deterministic hashed bag-of-words vector
   (256 dimensions, L2-normalised), not a neural embedding model.
   Retrieval is therefore real keyword-overlap cosine similarity
   over local text — not semantic in the neural sense, and not
   hardcoded fixture Q&A. Rephrases that share no words will miss
   retrieval and the cache, where a neural model might hit.
3. The 0.15 cosine-distance cache threshold is kept as the default
   (expressed as similarity >= 0.85) and is configurable; with hashed
   sparse vectors a one-word-changed rephrase passes it, while a
   synonym-heavy rephrase (e.g. "auth" vs "authentication") may not.
   This is a property of the local embedding, documented here.
4. Chunks are measured in words (~500 words, 50 words of overlap),
   standing in for the challenge's "~500 tokens": token counts depend
   on the chosen provider's tokenizer, which this build does not use.
5. "LLM" is a pluggable interface. Tests use `FakeLLM`, a generic
   extractive answerer: it scores retrieved chunk sentences against
   the question's content words, returns the best sentences with
   source citations, and answers "I don't have enough information"
   when no sentence overlaps. It contains no fixture questions or
   answers. An `OpenAICompatibleLLM` (stdlib HTTP, key from an
   environment variable, never hardcoded or requested here) is
   included for real use but was NOT verified against a live API —
   live LLM use needs the user's own key and is untested here.
6. Session follow-up "understanding" is keyword carry-over plus
   history in the prompt, not true pronoun coreference resolution;
   the fake provider cannot resolve "it" the way a real LLM would.
   Follow-up tests therefore assert history storage/isolation and
   retrieval on the follow-up's own content words, not coreference.
7. Long-term memory extraction is pattern-based ("I'm working on …",
   "I use …", "my project is …") with keyword topics, not the
   Memory Server's topic extraction / entity recognition / semantic
   search. Memory search is word-overlap over stored memories.
8. Summarisation is extractive condensation (topics of older
   messages plus a short summary line), not LLM summarisation.
9. The streaming endpoint is `POST /ask/stream` (SSE-style
   `data:` lines) rather than a separately specified path — the
   challenge only says a streaming endpoint is a nice addition.

## NOT built / NOT verified

- Redis Stack, Docker Compose, RedisVL, Redis Agent Memory Server,
  LiteLLM, any live LLM or embedding API call, the Pro Git book as a
  fixture corpus, and any real API key handling beyond reading an
  environment variable name in `OpenAICompatibleLLM`. No key was
  invented, hardcoded, or requested.
- The fyi detail-page URL and Step 6's closing test lines (see Gap).
- A browser UI: the challenge's "full-stack" surface is the REST API
  plus CLI in this build; no frontend is claimed.
