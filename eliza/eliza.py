#!/usr/bin/env python3
"""ELIZA: a rule-based chatbot (pattern matching, NOT an LLM).

Every reply is produced by a scripted rule loaded from a JSON script file
(see doctor.json and docs/SPEC.md): a keyword is found in the input, a
decomposition pattern splits the input into components, and a reassembly
template rebuilds those components (with pronoun reflection) into a reply.
If no rule matches, a stored memory reply or a context-free fallback is used.

Usage:
    python3 eliza.py [--script PATH]
"""

import argparse
import json
import re
import sys
from pathlib import Path

QUIT_WORDS = {"quit", "goodbye", "bye"}

REFLECTIONS = {
    "i": "you",
    "you": "i",
    "me": "you",
    "my": "your",
    "your": "my",
    "yours": "mine",
    "mine": "yours",
    "am": "are",
    "are": "am",
    "myself": "yourself",
    "yourself": "myself",
    "we": "you",
    "us": "you",
    "our": "your",
}

BANNER = (
    "ELIZA -- a rule-based chatbot (not an AI, not a language model).\n"
    "Replies come from scripted pattern-matching rules only.\n"
    "Type quit, goodbye, or bye to end the conversation."
)

MAX_REDIRECT_DEPTH = 10


def tokenize(text):
    """Lower-case, drop apostrophes, split on other punctuation."""
    cleaned = text.lower().replace("'", "")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return cleaned.split()


def is_quit(text):
    """True only when the whole input is one quit word (Step 1)."""
    words = tokenize(text)
    return len(words) == 1 and words[0] in QUIT_WORDS


def reflect(words):
    """Swap pronouns word by word; unknown words pass through."""
    return [REFLECTIONS.get(word, word) for word in words]


def match_decomposition(pattern, words):
    """Match a decomposition pattern against tokenized input.

    A pattern token '0' is a wildcard capturing any run of words
    (possibly empty). Any other token must match exactly. Returns a
    list of components, one per pattern token (each a list of words),
    or None if the pattern does not consume all input words. Wildcards
    take the fewest words that still let the rest of the pattern match.
    """
    def rec(pi, wi):
        if pi == len(pattern):
            return [] if wi == len(words) else None
        token = pattern[pi]
        if token == "0":
            for end in range(wi, len(words) + 1):
                rest = rec(pi + 1, end)
                if rest is not None:
                    return [words[wi:end]] + rest
            return None
        if wi < len(words) and token == words[wi]:
            rest = rec(pi + 1, wi + 1)
            if rest is not None:
                return [[words[wi]]] + rest
        return None

    return rec(0, 0)


def reassemble(template, components, wildcards):
    """Build a reply from a reassembly template.

    Numeric tokens are 1-based component references (counting every
    decomposition token, wildcards included). Captured wildcard text is
    pronoun-reflected; literal components and literal tokens are used
    as written.
    """
    out = []
    for token in template:
        if token.isdigit():
            index = int(token) - 1
            part = components[index]
            out.extend(reflect(part) if wildcards[index] else part)
        else:
            out.append(token)
    return format_reply(" ".join(out))


def format_reply(text):
    """Sentence-case a reply and tidy spacing before punctuation."""
    text = re.sub(r"\s+([.,?!;:])", r"\1", text.strip())
    if not text:
        return text
    text = text[0].upper() + text[1:]
    if text[-1] not in ".?!":
        text += "."
    return text


def load_script(path):
    """Load and validate a JSON script file. Raises ValueError."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            script = json.load(handle)
    except OSError as exc:
        raise ValueError("cannot read script file %s: %s" % (path, exc))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON in script file %s: %s" % (path, exc))
    if not isinstance(script, dict):
        raise ValueError("script file must contain a JSON object")
    for key in ("fallbacks",):
        if not isinstance(script.get(key), list) or not script[key]:
            raise ValueError("script must define a non-empty %r list" % key)
    for key in ("initial", "final"):
        if key in script and not isinstance(script[key], list):
            raise ValueError("script %r must be a list" % key)
    capacity = script.get("memory_capacity", 5)
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("script memory_capacity must be a positive integer")
    rules = script.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("script must define a non-empty rules list")
    keywords = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("each rule must be an object")
        keyword = rule.get("keyword")
        if not isinstance(keyword, str) or not keyword or len(keyword.split()) != 1:
            raise ValueError("each rule needs a single-word keyword")
        keyword = keyword.lower()
        if keyword in keywords:
            raise ValueError("duplicate keyword %r" % keyword)
        keywords.add(keyword)
        rule["keyword"] = keyword
        decomps = rule.get("decompositions")
        if not isinstance(decomps, list) or not decomps:
            raise ValueError("rule %r needs a non-empty decompositions list" % keyword)
        for decomp in decomps:
            pattern = decomp.get("pattern")
            if not isinstance(pattern, list) or not pattern or not all(
                isinstance(t, str) and t for t in pattern
            ):
                raise ValueError("rule %r has an invalid pattern" % keyword)
            reassemblies = decomp.get("reassemblies")
            if not isinstance(reassemblies, list) or not reassemblies:
                raise ValueError("rule %r needs reassemblies" % keyword)
            for template in reassemblies:
                if not isinstance(template, list) or not template:
                    raise ValueError("rule %r has an empty reassembly" % keyword)
                if len(template) == 1 and template[0].startswith("="):
                    continue  # redirection, validated at use time
                for token in template:
                    if token.isdigit() and not 1 <= int(token) <= len(pattern):
                        raise ValueError(
                            "rule %r reassembly token %r out of range" % (keyword, token)
                        )
        redirect = rule.get("redirect")
        if redirect is not None and not isinstance(redirect, str):
            raise ValueError("rule %r redirect must be a keyword string" % keyword)
    return script


class Eliza:
    """The rule engine. Pure apart from its counters and memory queue."""

    def __init__(self, script):
        self.script = script
        self.rules = {rule["keyword"]: rule for rule in script["rules"]}
        self.rule_order = [rule["keyword"] for rule in script["rules"]]
        self.counters = {}  # (keyword, decomposition index) -> next reassembly
        self.fallback_index = 0
        self.memory = []
        self.memory_capacity = script.get("memory_capacity", 5)

    def reply(self, text):
        """Return a reply string for user input (assumed not a quit)."""
        words = tokenize(text)
        if not words:
            return None
        matched = [kw for kw in self.rule_order if kw in words]
        for keyword in matched:
            result = self._apply_keyword(keyword, words, depth=0)
            if result is not None:
                return result
        if self.memory:
            return self.memory.pop(0)
        fallbacks = self.script["fallbacks"]
        result = fallbacks[self.fallback_index % len(fallbacks)]
        self.fallback_index += 1
        return format_reply(result)

    def _apply_keyword(self, keyword, words, depth):
        if depth > MAX_REDIRECT_DEPTH:
            return None
        rule = self.rules.get(keyword)
        if rule is None:
            return None
        for index, decomp in enumerate(rule["decompositions"]):
            components = match_decomposition(decomp["pattern"], words)
            if components is None:
                continue
            wildcards = [token == "0" for token in decomp["pattern"]]
            key = (keyword, index)
            counter = self.counters.get(key, 0)
            template = decomp["reassemblies"][counter % len(decomp["reassemblies"])]
            self.counters[key] = counter + 1
            if len(template) == 1 and template[0].startswith("="):
                return self._apply_keyword(template[0][1:].lower(), words, depth + 1)
            result = reassemble(template, components, wildcards)
            if decomp.get("memory"):
                self.memory.append(result)
                del self.memory[: max(0, len(self.memory) - self.memory_capacity)]
            return result
        redirect = rule.get("redirect")
        if redirect:
            return self._apply_keyword(redirect.lower(), words, depth + 1)
        return None


def default_script_path():
    return Path(__file__).resolve().parent / "doctor.json"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="ELIZA: a rule-based chatbot (pattern matching, not an LLM)."
    )
    parser.add_argument(
        "--script", default=str(default_script_path()), help="path to the JSON rule script"
    )
    args = parser.parse_args(argv)
    try:
        script = load_script(args.script)
    except ValueError as exc:
        print("eliza: %s" % exc, file=sys.stderr)
        return 2
    engine = Eliza(script)
    print(BANNER)
    for line in script.get("initial", []):
        print(format_reply(line))
    final = script.get("final", ["Goodbye."])
    try:
        while True:
            try:
                user_input = input("> ")
            except EOFError:
                break
            if is_quit(user_input):
                break
            result = engine.reply(user_input)
            if result is not None:
                print(result)
    except KeyboardInterrupt:
        print()
    for line in final:
        print(format_reply(line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
