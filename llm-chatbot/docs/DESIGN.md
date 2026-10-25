# DESIGN — LLM Powered AI Chatbot

## Layout

```
llm-chatbot/
  README.md
  chatbot.py          # the whole program (stdlib only)
  docs/
    SPEC.md           # challenge steps, source, divergences
    DESIGN.md         # this file
    TEST_PLAN.md
  tests/
    test_chatbot.py   # unittest suite, fake provider + local HTTP server only
```

One main file is intentional: the program is a thin loop
around a provider interface, and splitting it would add
indirection without benefit.

## Core types

```python
Message = {"role": "system"|"user"|"assistant", "content": str}
```

- `LLMProvider` (base class):
  - `complete(messages) -> str` — one full reply.
  - `stream(messages) -> Iterator[str]` — reply in chunks;
    the default implementation yields `complete(...)` once,
    so any provider gets streaming for free and providers
    that support real streaming override it.
  - Both raise `ValueError` on an empty message list, so a
    programming error fails loudly instead of sending an
    empty request.
- `FakeProvider(LLMProvider)`:
  - `complete` returns
    `Fake reply ({n} messages in history): {last user text}`
    where `n` is the number of messages it received. This
    makes history-passing directly observable in tests and
    in a demo run, without pretending to be intelligent.
  - `stream` yields the same reply word by word (with a
    trailing space except on the last word), so streamed
    output joins back to exactly the `complete` reply.
  - It records every `messages` list it receives in
    `self.seen` (a copy), which tests inspect to prove the
    system prompt and full history were sent.
- `HttpChatCompletionsProvider(LLMProvider)`:
  - Built on `urllib.request` / `urllib.error` only.
  - Endpoint: `{base_url}/chat/completions`
    (trailing slash on the base URL is stripped first).
  - `complete` POSTs
    `{"model": model, "messages": messages, "stream": false}`
    with `Authorization: Bearer <key>` and
    `Content-Type: application/json`, and returns
    `choices[0].message.content` (empty string if absent).
  - `stream` POSTs the same body with `"stream": true`,
    reads the SSE body line by line, ignores blank lines
    and `[DONE]`, parses each `data: {...}` line as JSON,
    and yields `choices[0].delta.content` pieces that are
    present and non-empty.
  - Constructor requires a non-empty API key and raises
    `ValueError` otherwise — it never invents or defaults
    a key. HTTP errors are re-raised as `RuntimeError`
    with the status and body snippet; malformed JSON
    likewise. No usage / token fields are read.
- `Conversation`:
  - Holds `system_prompt` (or `None`) and an ordered list
    of user/assistant messages.
  - `messages()` returns `[system?, *turns]`, applying
    `max_messages` if set: the system message is always
    kept and the oldest non-system turns are dropped
    until the total fits. `max_messages` below 1 (when a
    system prompt exists) keeps just the system message.
  - `add_user(text)`, `add_assistant(text)` — both reject
    empty/whitespace-only text with `ValueError` (the chat
    loop filters empty input before it ever gets here).
  - `clear()` drops turns, keeps the system prompt.
  - `transcript()` renders `role: content` lines for
    `/history`.
- `ChatBot`:
  - Wraps a provider + a conversation.
  - `ask(text) -> str`: adds the user turn, calls
    `provider.complete(messages())`, adds the assistant
    turn, returns the reply. On provider error the user
    turn stays in history and no assistant turn is added,
    so a retry is not polluted by an empty reply.
  - `ask_stream(text) -> Iterator[str]`: same, but calls
    `provider.stream(...)`, accumulates chunks, and adds
    exactly one assistant turn containing the joined text
    once the iterator is exhausted. If the iterator raises
    part-way, the partial text is still stored (it was
    shown to the user) — this is tested.
- `run_chat(bot, input_stream, output_stream, use_stream=True)`:
  - Prints a short banner, then loops printing
    `Your query: ` (no newline, flushed), reading a line.
  - EOF ends the session cleanly. `exit`, `quit`,
    `/exit`, `/quit` (case-insensitive, surrounding
    whitespace stripped) end it. Empty lines are ignored.
  - `/help`, `/history`, `/clear` are handled locally and
    never sent to the provider.
  - For a normal query it calls `ask` (printing the reply
    on its own line) or `ask_stream` (printing chunks as
    they arrive, then a final newline).
  - Provider errors are printed as `Error: ...` and the
    loop continues — one failed turn does not kill the
    session.

## CLI (`chatbot.py` as a script)

```
python3 chatbot.py [--provider fake|http] [--system TEXT]
                   [--model MODEL] [--base-url URL]
                   [--api-key-env NAME] [--max-messages N]
                   [--stream | --no-stream]
```

- Defaults: `--provider fake`, streaming on, no history
  cap, default system prompt:
  "You are a helpful assistant. Answer in a few short sentences."
- `--provider http` requires `LLM_API_KEY` (or the env var
  named by `--api-key-env`) to be set and non-empty;
  otherwise the program exits with a clear message telling
  the user to supply their own key. It never prompts for,
  prints, or stores a key.
- `--model` / `--base-url` fall back to `LLM_MODEL` /
  `LLM_BASE_URL` env vars, then to `gpt-4o-mini` /
  `https://api.openai.com/v1` defaults. Those defaults
  are endpoint/model *names* for a user-supplied
  OpenAI-compatible account, not credentials and not a
  claim that such an account was tested.
- `--max-messages 0` (or negative) means no cap.

## Data flow (one turn)

```
user input -> Conversation.add_user
           -> provider.complete/stream(system + history + new user turn)
           -> chunks printed (streaming) / reply printed
           -> Conversation.add_assistant(joined reply)
```

Every request therefore carries the full (possibly
capped) history, which is exactly the page's step 5:
a follow-up is interpreted by the model in the context
of earlier turns, because the earlier turns are re-sent.
