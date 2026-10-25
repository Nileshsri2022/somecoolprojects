#!/usr/bin/env python3
"""Spelling correction tool (codingchallenges.fyi, challenge-spelling-correction).

Steps 0-5 of the challenge: load a word-frequency table, report
known words as correct, and suggest corrections by generating
all words one edit away (deletion, insertion, transposition,
replacement), falling back to distance two, ranking by lowest
distance first and then highest frequency.

Usage:
    python3 spell_correct.py DICT word [word ...]
    python3 spell_correct.py DICT --correct "some text"
    python3 spell_correct.py DICT --file input.txt
    python3 spell_correct.py DICT --suggestions 3 word
    python3 spell_correct.py DICT --time word [word ...]

Dictionary format: one word per line, optionally followed by
a frequency ("word 123", "word\\t123", or "word,123"). A bare
word means frequency 1. Blank lines and "#" comments ignored.
Standard library only.
"""

import argparse
import re
import string
import sys
import time
from pathlib import Path

ALPHABET = string.ascii_lowercase
_WORD_RE = re.compile(r"[A-Za-z]+")


def load_dictionary(path):
    """Load a word-frequency table from path.

    Returns dict mapping lowercase word -> frequency (int).
    Duplicate words add their frequencies. Raises
    FileNotFoundError for a missing file and ValueError for a
    malformed frequency.
    """
    freq = {}
    with open(path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # Split on whitespace, tab, or a single comma.
            parts = re.split(r"[\s,]+", line)
            word = parts[0].lower()
            if not word:
                continue
            count = 1
            if len(parts) > 1:
                try:
                    count = int(parts[1])
                except ValueError:
                    raise ValueError(
                        f"bad frequency in dictionary line: {raw_line.strip()!r}"
                    ) from None
            freq[word] = freq.get(word, 0) + count
    return freq


def is_correct(word, freq):
    """True if word (case-insensitive) is in the frequency table."""
    return word.lower() in freq


def edits1(word):
    """All strings one edit away from word.

    Deletion, transposition, replacement, insertion, over a-z.
    Count for length n: n + (n - 1) + 26n + 26(n + 1) = 54n + 25
    before deduplication (see docs/DESIGN.md).
    """
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    deletes = [left + right[1:] for left, right in splits if right]
    transposes = [
        left + right[1] + right[0] + right[2:]
        for left, right in splits
        if len(right) > 1
    ]
    replaces = [
        left + c + right[1:] for left, right in splits if right for c in ALPHABET
    ]
    inserts = [left + c + right for left, right in splits for c in ALPHABET]
    return set(deletes + transposes + replaces + inserts)


def known(words, freq):
    """The subset of words present in the frequency table."""
    return {word for word in words if word in freq}


def rank(words, freq):
    """Rank candidates: highest frequency first, alphabetical on ties."""
    return sorted(words, key=lambda w: (-freq[w], w))


def suggest(word, freq, limit=None):
    """Ranked correction suggestions for word (lowest distance first).

    Distance-1 candidates ranked first, then distance-2, each
    group frequency-descending with an alphabetical tie-break.
    Returns [] when the word is correct or has no candidate.
    """
    word = word.lower()
    if not word or word in freq or not word.isalpha() or not word.isascii():
        return []
    distance1 = rank(known(edits1(word), freq), freq)
    if distance1:
        suggestions = distance1
    else:
        distance2 = set()
        for edit in edits1(word):
            distance2.update(known(edits1(edit), freq))
        suggestions = rank(distance2, freq)
    if limit is not None:
        suggestions = suggestions[:limit]
    return suggestions


def correct(word, freq):
    """Best correction for word, or the word itself (lowercased).

    Known words echo unchanged; words with no candidate at
    distance 1 or 2 also echo unchanged.
    """
    word = word.lower()
    suggestions = suggest(word, freq, limit=1)
    return suggestions[0] if suggestions else word


def correct_text(text, freq):
    """Correct each ASCII-letter word in text, preserving the rest.

    An initial capital on a word is preserved on its correction.
    """

    def replace(match):
        token = match.group(0)
        fixed = correct(token, freq)
        if token[0].isupper():
            fixed = fixed[:1].upper() + fixed[1:]
        return fixed

    return _WORD_RE.sub(replace, text)


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Suggest spelling corrections from a word-frequency dictionary."
    )
    parser.add_argument("dictionary", help="dictionary file (word [frequency] per line)")
    parser.add_argument("words", nargs="*", help="words to correct")
    parser.add_argument("--correct", metavar="TEXT", help="correct this text and print it")
    parser.add_argument("--file", metavar="PATH", help="correct the text in this file and print it")
    parser.add_argument(
        "--suggestions",
        type=int,
        metavar="N",
        help="print up to N ranked suggestions per word instead of one correction",
    )
    parser.add_argument("--time", action="store_true", help="append the timing line (Step 5)")
    # parse_intermixed_args: a nargs="*" positional otherwise makes
    # argparse reject optionals placed after/before the word list.
    args = parser.parse_intermixed_args(argv)
    if args.suggestions is not None and args.suggestions < 1:
        parser.error("--suggestions must be at least 1")
    if (args.correct is not None or args.file is not None) and args.suggestions is not None:
        parser.error("--suggestions cannot be combined with --correct/--file")
    if args.correct is not None and args.file is not None:
        parser.error("use only one of --correct and --file")
    if args.correct is None and args.file is None and not args.words:
        parser.error("give words to correct, or --correct/--file text")
    return args


def main(argv=None):
    args = _parse_args(argv)
    try:
        freq = load_dictionary(args.dictionary)
    except FileNotFoundError:
        print(f"error: dictionary file not found: {args.dictionary}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as exc:
        print(f"error: cannot load dictionary: {exc}", file=sys.stderr)
        return 1

    if args.correct is not None:
        print(correct_text(args.correct, freq))
        return 0
    if args.file is not None:
        try:
            text = Path(args.file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot read file: {exc}", file=sys.stderr)
            return 1
        print(correct_text(text, freq), end="" if text.endswith("\n") else "\n")
        return 0

    start = time.perf_counter()
    lines = []
    for word in args.words:
        if args.suggestions is not None:
            suggestions = suggest(word, freq, limit=args.suggestions)
            lines.append(f"{word}: {', '.join(suggestions)}")
        else:
            lines.append(f"{word} {correct(word, freq)}")
    elapsed_ms = (time.perf_counter() - start) * 1000
    print("\n".join(lines))
    if args.time:
        rate = len(args.words) / (elapsed_ms / 1000) if elapsed_ms > 0 else float("inf")
        print(f"Time : {elapsed_ms:.6f}ms {rate:.1f} words per second")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
