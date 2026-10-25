# SPEC — LLM Powered AI Chatbot

## Challenge source (resolved, read before writing anything)

- Challenge: **Build Your Own LLM Powered AI Chatbot**,
  Coding Challenge #102, published 2025-11-22.
- Found via the site's tag pages, as instructed:
  `https://codingchallenges.fyi/challenges/tags` →
  `https://codingchallenges.fyi/challenges/tags/ai` (and
  `…/tags/artificial-intelligence`), both of which list
  "Build Your Own LLM Powered AI Chatbot".
- Full challenge text read from the challenge's original
  newsletter version (the same challenge, same author, same steps):
  `https://codingchallenges.substack.com/p/coding-challenge-102-llm-powered`
- Note on verification: a direct fetch of the fyi challenge
  page itself was rate-limited once (HTTP 429 from the fetch
  service) and was not retried in that form. The tag pages
  confirm the challenge exists on codingchallenges.fyi under
  the `ai` / `artificial intelligence` tags, and the full step
  text above was read end-to-end. No fyi challenge slug is
  guessed or claimed here.

## What the page asks for

The page is deliberately stack-free: "a challenge you could
do with a web-based UI, a desktop or mobile UI or even a
terminal based UI. The choice is yours. I personally went
for a terminal based UI." Its steps, in order:

1. **Single prompt via an LLM API.** Pick a model (local via
   Ollama, or ChatGPT / Claude / Gemini / another provider),
   get an API key, choose the provider API or a model-neutral
   one such as LangChain. Hard-code a prompt, connect, get a
   response, display it.
2. **Chat loop.** Keep asking the user for prompts; on each
   prompt send it to the model and display the response.
   The page's example transcript uses the prompt
   `Your query: `.
3. **Streaming mode.** Stream the answer to the console so
   large responses start appearing immediately instead of
   after several seconds. If streaming was already chosen,
   proceed to step 4.
4. **System prompt / system instructions.** Configure the
   model with rules, behaviour and constraints. The page's
   mini example makes the bot "John", a software engineer
   who writes Coding Challenges, using only a few sentences;
   a second example makes a "Dad" bot that refuses manga /
   graphic novels, explains why in one or two sentences, and
   likes Dad jokes. The user may invent their own
   personality — it does not have to behave like John.
5. **Conversation history (multi-turn).** Each LLM call is
   otherwise stateless, so a follow-up such as "Why do you
   suggest that one?" loses the referent. Include the chat
   history in each request so follow-ups resolve against
   earlier turns.
6. **Optional extension.** "You can take this further by
   adding more context to the model." No specific mechanism
   is prescribed.

## What this build does

- Terminal UI, as the author chose, in Python 3 standard
  library only: `chatbot.py`.
- `Your query: ` prompt, matching the page's transcript.
- A pluggable provider interface (`LLMProvider`) with two
  implementations:
  - `FakeProvider` — a local, deterministic, offline stand-in
    used by default and by every test. It echoes the last
    user message and reports how many messages of history it
    received, so history-passing is observable without any
    real model.
  - `HttpChatCompletionsProvider` — an OpenAI-compatible
    chat-completions client over `urllib` (JSON for normal
    replies, server-sent-events parsing for streaming). It
    reads the key only from the environment
    (`LLM_API_KEY`, overridable via `--api-key-env`), the
    base URL from `--base-url` / `LLM_BASE_URL`, and the
    model from `--model` / `LLM_MODEL`. It is scaffolding
    for a user-supplied provider; see "NOT built / NOT
    verified" below.
- System prompt via `--system` (or a built-in default
  personality, see DESIGN.md). The system message is always
  the first message sent to the provider.
- Full conversation history sent on every request
  (system + all user/assistant turns, oldest first), with an
  optional `--max-messages` cap that keeps the system message
  and drops the oldest non-system turns first.
- Streaming by default (`--no-stream` disables it);
  streamed chunks are printed as they arrive and joined
  into the single assistant message stored in history.
- Loop commands: `exit` / `quit` (also `/exit`, `/quit`,
  Ctrl-D / EOF) end the session; `/history` prints the
  stored transcript; `/clear` resets history but keeps the
  system prompt; `/help` lists the commands. Empty input
  is ignored, not sent.

## Deliberate divergences

1. **No real LLM provider is the default, and no real
   provider SDK is used.** The page says "grab yourself an
   API key" and pick a provider SDK / LangChain. This build
   uses stdlib-only HTTP instead of any vendor SDK, and
   defaults to the fake provider, so the program runs and
   is testable with no key, no account and no network.
   This is a deliberate, documented divergence, required
   by the build brief (never invent, hardcode or request
   real API keys).
2. **Model-neutral HTTP, not LangChain / a vendor SDK.**
   The page allows "a model-neutral one like LangChain";
   stdlib HTTP to an OpenAI-compatible endpoint is the
   stdlib-only equivalent. Provider-specific request
   shapes (e.g. Anthropic's) are NOT implemented.
3. **Extra loop commands** (`/history`, `/clear`, `/help`)
   are small usability additions not in the page. They do
   not change any page step.
4. **History cap is optional and off by default.**
   The page does not mention a cap; the cap exists only so
   a long session can be bounded, and it never drops the
   system message.
5. **Default system prompt is a generic helper**, not
   John's persona and not the "Dad" bot. The page
   explicitly allows inventing your own personality. The
   John's-persona text from the page is NOT copied as the
   default; users can pass any system prompt with
   `--system`.

## NOT built / NOT verified — stated honestly

- **No live LLM call was made or verified here.** No API
  key was created, supplied, hardcoded or requested, and
  no real model (ChatGPT, Claude, Gemini, Ollama or any
  other) was used, contacted or tested. A live call needs
  the user's own key and provider, e.g.:
  `LLM_API_KEY=<your own key> python3 chatbot.py --provider http --model <your model>`.
  Until a user does that, the HTTP provider is
  untested-against-a-real-endpoint scaffolding.
- **No intelligence is claimed.** The default fake
  provider only echoes; it does not understand, reason or
  know anything. Any "intelligence" in a live run would
  come entirely from the user's chosen model, not from
  this code.
- **No web / desktop / mobile UI**, only the terminal UI
  the page's author also chose.
- **No LangChain, no vendor SDK, no RAG / retrieval,
  no tool/function calling, no persistent chat storage,
  no multi-user or server mode.** The page's optional
  "more context" extension beyond history is not built.
- **No token counting / cost tracking.** The HTTP
  provider does not parse usage fields.
- Provider error handling is limited to surfacing HTTP
  and JSON errors as a readable message and ending that
  turn without corrupting history (the failed user turn
  stays; no empty assistant message is stored).
