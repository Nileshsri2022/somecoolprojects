#!/usr/bin/env python3
"""LLM Powered AI Chatbot (Coding Challenge #102).

Terminal chatbot with a pluggable provider interface, a
system prompt, streaming replies, and full conversation
history sent on every request.

Providers:
  * FakeProvider -- local, deterministic, offline stand-in
    (the default). It echoes the last user message and
    reports how many messages of history it received. It
    is NOT intelligent and no real model is involved.
  * HttpChatCompletionsProvider -- OpenAI-compatible chat
    completions over stdlib urllib (JSON + SSE streaming).
    It needs the user's own API key from the environment;
    it never invents, hardcodes, prints, or stores a key.

Standard library only. See docs/SPEC.md for the challenge
steps, divergences, and what was NOT built or verified.
"""

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Iterator, List, Optional

Message = dict  # {"role": "system"|"user"|"assistant", "content": str}

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer in a few short sentences."
)
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
PROMPT = "Your query: "
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit"}
HELP_TEXT = (
    "Commands: exit/quit (end), /history (show transcript), "
    "/clear (reset history, keep system prompt), /help (this list)."
)


def _require_messages(messages: List[Message]) -> None:
    if not messages:
        raise ValueError("no messages to send to the provider")


def _last_user_text(messages: List[Message]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


class LLMProvider:
    """Pluggable chat-model interface."""

    def complete(self, messages: List[Message]) -> str:
        raise NotImplementedError

    def stream(self, messages: List[Message]) -> Iterator[str]:
        """Yield reply chunks; default is one chunk = full reply."""
        yield self.complete(messages)


class FakeProvider(LLMProvider):
    """Deterministic offline stand-in. Echoes; not intelligent."""

    def __init__(self) -> None:
        self.seen: List[List[Message]] = []

    def complete(self, messages: List[Message]) -> str:
        _require_messages(messages)
        # Copy, so later conversation edits don't rewrite history.
        self.seen.append([dict(m) for m in messages])
        return (
            f"Fake reply ({len(messages)} messages in history): "
            f"{_last_user_text(messages)}"
        )

    def stream(self, messages: List[Message]) -> Iterator[str]:
        reply = self.complete(messages)
        words = reply.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")


class HttpChatCompletionsProvider(LLMProvider):
    """OpenAI-compatible chat completions client (stdlib urllib).

    Never called with a real key in this project's tests or
    demo runs; tests point it at a local HTTP server only.
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL,
                 base_url: str = DEFAULT_BASE_URL) -> None:
        if not api_key:
            raise ValueError(
                "no API key supplied: set LLM_API_KEY (or the variable "
                "named by --api-key-env) to your own key"
            )
        self.api_key = api_key
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"

    def _request(self, messages: List[Message], stream: bool) -> urllib.request.Request:
        body = json.dumps(
            {"model": self.model, "messages": messages, "stream": stream}
        ).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, method="POST")
        request.add_header("Authorization", f"Bearer {self.api_key}")
        request.add_header("Content-Type", "application/json")
        return request

    def _read_response(self, response) -> dict:
        try:
            return json.loads(response.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise RuntimeError(f"provider returned malformed JSON: {exc}") from exc

    def complete(self, messages: List[Message]) -> str:
        _require_messages(messages)
        try:
            with urllib.request.urlopen(self._request(messages, False)) as response:
                payload = self._read_response(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"provider HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"provider request failed: {exc.reason}") from exc
        try:
            return payload["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected provider response shape: {payload!r}") from exc

    def stream(self, messages: List[Message]) -> Iterator[str]:
        _require_messages(messages)
        try:
            response = urllib.request.urlopen(self._request(messages, True))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"provider HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"provider request failed: {exc.reason}") from exc
        with response:
            for raw_line in response:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    payload = json.loads(data)
                except ValueError as exc:
                    raise RuntimeError(f"provider returned malformed SSE JSON: {exc}") from exc
                try:
                    chunk = payload["choices"][0]["delta"].get("content")
                except (KeyError, IndexError, TypeError):
                    continue
                if chunk:
                    yield chunk


class Conversation:
    """System prompt + ordered user/assistant turns."""

    def __init__(self, system_prompt: Optional[str] = None,
                 max_messages: int = 0) -> None:
        self.system_prompt = system_prompt
        self.max_messages = max_messages  # <= 0 means no cap
        self._turns: List[Message] = []

    def _check_text(self, text: str) -> str:
        if not text or not text.strip():
            raise ValueError("message text must not be empty")
        return text

    def add_user(self, text: str) -> None:
        self._turns.append({"role": "user", "content": self._check_text(text)})

    def add_assistant(self, text: str) -> None:
        self._turns.append({"role": "assistant", "content": self._check_text(text)})

    def messages(self) -> List[Message]:
        all_messages: List[Message] = []
        if self.system_prompt:
            all_messages.append({"role": "system", "content": self.system_prompt})
        all_messages.extend(self._turns)
        if self.max_messages > 0 and len(all_messages) > self.max_messages:
            if self.system_prompt:
                # Always keep the system message; drop oldest turns first.
                keep = self.max_messages - 1
                all_messages = all_messages[:1] + all_messages[1:][-keep:] if keep > 0 else all_messages[:1]
            else:
                all_messages = all_messages[-self.max_messages:]
        return all_messages

    def clear(self) -> None:
        self._turns = []

    def transcript(self) -> str:
        return "\n".join(
            f"{m['role']}: {m['content']}" for m in self.messages()
        )


class ChatBot:
    """Conversation + provider; one turn = user turn + assistant turn."""

    def __init__(self, provider: LLMProvider, conversation: Conversation) -> None:
        self.provider = provider
        self.conversation = conversation

    def ask(self, text: str) -> str:
        self.conversation.add_user(text)  # raises on empty input
        try:
            reply = self.provider.complete(self.conversation.messages())
        except Exception:
            # Failed turn: user turn stays, no empty assistant turn stored.
            raise
        self.conversation.add_assistant(reply)
        return reply

    def ask_stream(self, text: str) -> Iterator[str]:
        self.conversation.add_user(text)
        chunks: List[str] = []
        try:
            for chunk in self.provider.stream(self.conversation.messages()):
                chunks.append(chunk)
                yield chunk
        finally:
            # Store whatever was shown, even if the stream failed part-way.
            # (If nothing was shown and it failed, there is nothing to store:
            # add_assistant rejects empty text, so guard that case.)
            joined = "".join(chunks)
            if joined:
                self.conversation.add_assistant(joined)


def run_chat(bot: ChatBot, input_stream=None, output_stream=None,
             use_stream: bool = True) -> None:
    """Terminal loop. input/output default to sys.stdin/sys.stdout."""
    in_stream = input_stream if input_stream is not None else sys.stdin
    out = output_stream if output_stream is not None else sys.stdout

    def write(text: str) -> None:
        out.write(text)
        out.flush()

    write("LLM Powered AI Chatbot (type exit to quit, /help for commands)\n")
    while True:
        write(PROMPT)
        line = in_stream.readline()
        if not line:  # EOF / Ctrl-D
            break
        query = line.strip()
        if not query:
            continue
        lowered = query.lower()
        if lowered in EXIT_COMMANDS:
            break
        if lowered == "/help":
            write(HELP_TEXT + "\n")
            continue
        if lowered == "/history":
            transcript = bot.conversation.transcript()
            write((transcript + "\n") if transcript else "(no history yet)\n")
            continue
        if lowered == "/clear":
            bot.conversation.clear()
            write("History cleared.\n")
            continue
        try:
            if use_stream:
                for chunk in bot.ask_stream(query):
                    write(chunk)
                write("\n")
            else:
                write(bot.ask(query) + "\n")
        except Exception as exc:  # one failed turn must not kill the session
            write(f"Error: {exc}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM Powered AI Chatbot")
    parser.add_argument("--provider", choices=["fake", "http"], default="fake",
                        help="fake (default, offline) or http (OpenAI-compatible, needs your own key)")
    parser.add_argument("--system", default=DEFAULT_SYSTEM_PROMPT,
                        help="system prompt / instructions for the chatbot")
    parser.add_argument("--model", default=None,
                        help="model name (default: $LLM_MODEL or gpt-4o-mini)")
    parser.add_argument("--base-url", default=None,
                        help="API base URL (default: $LLM_BASE_URL or https://api.openai.com/v1)")
    parser.add_argument("--api-key-env", default="LLM_API_KEY",
                        help="env var holding your own API key (default LLM_API_KEY)")
    parser.add_argument("--max-messages", type=int, default=0,
                        help="cap on messages sent per request, 0 = no cap (system message always kept)")
    stream_group = parser.add_mutually_exclusive_group()
    stream_group.add_argument("--stream", dest="use_stream", action="store_true",
                              help="stream replies (default)")
    stream_group.add_argument("--no-stream", dest="use_stream", action="store_false",
                              help="wait for the full reply before printing")
    parser.set_defaults(use_stream=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.provider == "fake":
        provider: LLMProvider = FakeProvider()
    else:
        api_key = os.environ.get(args.api_key_env, "")
        if not api_key:
            print(
                f"Error: {args.api_key_env} is not set. This program never "
                "invents or stores a key -- set it to your own provider key "
                "and retry, or run without --provider http to use the offline "
                "fake provider.",
                file=sys.stderr,
            )
            return 2
        provider = HttpChatCompletionsProvider(
            api_key,
            model=args.model or os.environ.get("LLM_MODEL", DEFAULT_MODEL),
            base_url=args.base_url or os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL),
        )
    conversation = Conversation(system_prompt=args.system,
                                max_messages=args.max_messages)
    run_chat(ChatBot(provider, conversation), use_stream=args.use_stream)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
