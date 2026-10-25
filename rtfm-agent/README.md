# rtfm-agent — Build Your Own RTFM For Me Agent

Coding Challenge #110, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

An AI documentation assistant: ingest markdown/text docs, chunk and
index them, and answer questions from the retrieved chunks with
source citations — using retrieval-augmented generation (RAG),
semantic caching, session memory, and long-term memory. Python 3
standard library only; no Redis server, no live LLM, no API keys.

## Usage

The REST API is the main surface (the CLI holds no persistent store
across invocations — each CLI run starts with an empty index, so
`ask` alone on a fresh process honestly answers that it has no
information; use `serve` for a stateful assistant):

```sh
python3 rtfm_agent.py serve --port 8000
curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
  -d '{"source": "api-reference.md", "text": "# API Reference\n\n## Authentication\n\nTo authenticate, send your API key in the Authorization header."}'
curl -X POST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "How do I authenticate to the API?"}'
curl localhost:8000/metrics
curl -X POST localhost:8000/cache/flush
```

CLI helpers:

```sh
python3 rtfm_agent.py ingest docs/*.md
python3 rtfm_agent.py tell "I'm working on the payments microservice in Go"
python3 rtfm_agent.py serve --port 8000
```

Endpoints: `POST /ingest`, `POST /ask`, `POST /ask/stream`
(SSE-style), `GET /metrics`, `POST /cache/flush`, `GET /health`.

Answers cite their source files. A question the docs do not cover
gets an honest "I don't have enough information" reply instead of
an invented answer. Live LLM use needs the user's own key via
`OpenAICompatibleLLM` and was not verified here — tests use the
local `FakeLLM` and local fixture documents only.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

37 tests, all passing: chunking/overlap/sections, hashed-vector
retrieval and metadata filters, dedupe on re-ingest, cited and
honest answers, multi-document citations, semantic cache
(hit/rephrase/miss/flush/metrics), session history, isolation and
TTL, long-term memory across sessions, hybrid search boost,
summarisation, graceful degradation with broken cache/memory, the
REST API on an ephemeral port, and the CLI.

## Files

- `rtfm_agent.py` — chunking, hashed embeddings, vector index,
  providers, semantic cache, sessions, memory, agent, REST API, CLI.
- `docs/SPEC.md` — challenge steps, resolved page URLs, divergences,
  and everything not built, honestly.
- `docs/DESIGN.md` — component design.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_rtfm_agent.py` — the test suite.
