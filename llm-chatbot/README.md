# LLM Powered AI Chatbot

A terminal LLM-powered chatbot, built for Coding Challenge
#102 ("Build Your Own LLM Powered AI Chatbot",
`https://codingchallenges.substack.com/p/coding-challenge-102-llm-powered`,
also listed under the `ai` / `artificial intelligence` tags
at `https://codingchallenges.fyi/challenges/tags/ai`).
Python 3 standard library only — no third-party packages.

## Run

```sh
python3 chatbot.py
```

This uses a local fake provider by default, so it runs
offline with no API key. Type a query at the `Your query: `
prompt; `exit` (or `quit`, Ctrl-D) ends the session.
`/history` shows the transcript, `/clear` resets it,
`/help` lists commands.

```sh
# Example session (fake provider):
#   Your query: What is wc?
#   Fake reply (2 messages in history): What is wc?
```

## Use a real provider (your own key required)

No key is included, hardcoded, or requested by this
program. To use a real OpenAI-compatible endpoint, supply
your own key and model:

```sh
LLM_API_KEY=<your own key> python3 chatbot.py --provider http --model <your model>
# Optional: --base-url <your endpoint>  (default https://api.openai.com/v1)
# Optional: --api-key-env <OTHER_ENV_VAR> to read the key from elsewhere
```

Other options: `--system "Your system prompt here"`,
`--max-messages N` (0 = no cap), `--no-stream` to disable
streaming (streaming is on by default).

**Honest limits:** no live LLM call was made or verified
while building this — the HTTP provider is scaffolding
for a user-supplied provider, and the default fake
provider only echoes; it is not intelligent and no real
model was used. See `docs/SPEC.md` for the full list of
divergences and scope limits.

## Files

- `chatbot.py` — the whole program (provider interface,
  fake + HTTP providers, conversation history, chat loop, CLI)
- `docs/SPEC.md` — challenge steps, resolved source URL,
  divergences, what was NOT built
- `docs/DESIGN.md` — design and data flow
- `docs/TEST_PLAN.md` — test coverage and how to run it
- `tests/test_chatbot.py` — unittest suite (fake provider
  and a local ephemeral-port HTTP server only; never a
  real LLM API)

## Tests

```sh
python3 -m unittest discover -s tests -v
```
