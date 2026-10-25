# TEST_PLAN — LLM Powered AI Chatbot

## Rules

- Every test uses the local `FakeProvider` or a local
  HTTP server started on an ephemeral port
  (`port 0`, OS-assigned) in the test process itself.
- **No test contacts a real LLM API, the internet, or
  any external service.** The HTTP-provider tests point
  at `http://127.0.0.1:<ephemeral>` and the server is
  shut down in `tearDown`.
- Run with: `python3 -m unittest discover -s tests -v`
  from `llm-chatbot/`.

## Coverage

### Conversation
- System prompt, when given, is the first message and
  has role `system`; with no system prompt there is no
  system message.
- User/assistant turns append in order with correct roles.
- Empty / whitespace-only user or assistant text raises
  `ValueError`.
- `clear()` drops turns but keeps the system prompt.
- `max_messages` keeps the system message and drops the
  oldest non-system turns first; a cap that fits only the
  system message keeps just it; no cap keeps everything.
- `transcript()` renders one `role: content` line per
  message, including the system line.

### FakeProvider
- `complete` echoes the last user message and reports the
  history length it received, proving history is passed.
- `complete` on an empty message list raises `ValueError`.
- `stream` chunks join back to exactly the `complete`
  reply for the same messages.
- `seen` records a copy of each messages list received
  (mutating the conversation afterwards does not rewrite
  the recorded copy).

### ChatBot
- `ask` stores user + assistant turns in order and
  returns the provider reply; the provider receives the
  system message plus all prior turns.
- A second `ask` receives the first turn's history, i.e.
  multi-turn context is actually sent (the page's step 5).
- `ask` on empty input raises `ValueError` and stores
  nothing.
- `ask` with a failing provider stores the user turn,
  stores no assistant turn, and propagates the error.
- `ask_stream` stores exactly one assistant turn equal
  to the joined chunks, and yields the same chunks.
- `ask_stream` with a provider that fails part-way
  stores the partial text that was already yielded.

### HttpChatCompletionsProvider (local server only)
- `complete` POSTs JSON with the model and the full
  messages, sends `Authorization: Bearer <key>`, and
  returns `choices[0].message.content`.
- `stream` parses an SSE body (`data: {...}` lines,
  `[DONE]` terminator, blank lines ignored) into the
  concatenated delta contents.
- Constructor with an empty key raises `ValueError`
  (no key is ever invented).
- An HTTP error status raises `RuntimeError` naming the
  status; the message body snippet is included.
- A malformed JSON response raises `RuntimeError`.

### Chat loop (`run_chat`, StringIO in/out)
- A query is answered with the `Your query: ` prompt and
  the reply printed; `exit` (and `quit`, `/exit`, EOF)
  ends the session without sending a further query.
- Empty lines are ignored, not sent to the provider.
- `/history` prints the transcript and does not call the
  provider; `/clear` resets turns (system kept) without
  calling the provider; `/help` prints command help.
- Streaming mode prints chunks as they arrive followed
  by a newline; non-streaming mode prints the whole reply.
- A provider error prints `Error: ...` and the loop
  continues to the next query instead of crashing.

### Manual checks (not automated, and not claimed as done)
- Live run against a user-supplied provider:
  `LLM_API_KEY=<own key> python3 chatbot.py --provider http`
  — NOT performed here; needs the user's own key.
- Demo run with the fake provider:
  `python3 chatbot.py` then a query, `/history`, `exit`.
