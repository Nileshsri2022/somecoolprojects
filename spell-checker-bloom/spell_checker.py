#!/usr/bin/env python3
"""Spell checker using a Bloom filter (Coding Challenge #53).

Usage:
    python3 spell_checker.py -build dict.txt [words.bf]
    python3 spell_checker.py -build dict.txt -o words.bf [--fp-rate 0.01]
    python3 spell_checker.py words.bf word1 word2 ...

A Bloom filter is probabilistic: a word it reports absent is
definitely not in the dictionary, and a word it reports present
is only *probably* in it. It can never produce a false negative,
but it can produce false positives. See docs/DESIGN.md.

File format (big-endian, per the challenge page):
    0   4 bytes  b"CCBF"
    4   2 bytes  version (1)
    6   2 bytes  number of hash functions
    8   4 bytes  number of bits
    12  ...      bit array, ceil(num_bits / 8) bytes

Python 3 standard library only.
"""

import math
import os
import sys

MAGIC = b"CCBF"
VERSION = 1
HEADER_SIZE = 12
DEFAULT_FP_RATE = 0.01
DEFAULT_OUTPUT = "words.bf"

_FNV_OFFSET = 0xCBF29CE484222325
_FNV_PRIME = 0x100000001B3
_MASK64 = (1 << 64) - 1


def _fnv1a_64(word):
    """FNV-1a 64-bit hash: xor each byte, then multiply."""
    h = _FNV_OFFSET
    for byte in word.encode("utf-8"):
        h ^= byte
        h = (h * _FNV_PRIME) & _MASK64
    return h


def _fnv1_64(word):
    """FNV-1 64-bit hash: multiply each byte, then xor."""
    h = _FNV_OFFSET
    for byte in word.encode("utf-8"):
        h = (h * _FNV_PRIME) & _MASK64
        h ^= byte
    return h


def _normalize(word):
    return word.strip().lower()


def optimal_parameters(n, fp_rate):
    """Return (num_bits, num_hashes) for n items at fp_rate.

    m = ceil(-n * ln(p) / (ln 2)^2)
    k = round((m / n) * ln 2), at least 1.
    """
    if n <= 0:
        raise ValueError("expected item count must be positive")
    if not 0 < fp_rate < 1:
        raise ValueError("false-positive rate must be between 0 and 1")
    num_bits = max(1, math.ceil(-n * math.log(fp_rate) / (math.log(2) ** 2)))
    num_hashes = max(1, round((num_bits / n) * math.log(2)))
    return num_bits, num_hashes


class BloomFilter:
    """A bit array with k double-hashed positions per item."""

    def __init__(self, num_bits, num_hashes):
        if num_bits <= 0:
            raise ValueError("num_bits must be positive")
        if num_hashes <= 0:
            raise ValueError("num_hashes must be positive")
        self.num_bits = num_bits
        self.num_hashes = num_hashes
        self._bytes = bytearray((num_bits + 7) // 8)

    def _positions(self, word):
        h1 = _fnv1a_64(word)
        h2 = _fnv1_64(word) | 1  # odd step: reaches every bit position
        return [(h1 + i * h2) % self.num_bits for i in range(self.num_hashes)]

    def add(self, word):
        word = _normalize(word)
        if not word:
            raise ValueError("cannot add an empty word")
        for pos in self._positions(word):
            self._bytes[pos // 8] |= 1 << (pos % 8)

    def __contains__(self, word):
        word = _normalize(word)
        if not word:
            return False
        return all(
            self._bytes[pos // 8] & (1 << (pos % 8))
            for pos in self._positions(word)
        )

    @property
    def bits_set(self):
        return sum(bin(byte).count("1") for byte in self._bytes)

    def estimated_false_positive_rate(self, n):
        """Theoretical rate (1 - exp(-k*n/m)) ** k for n items."""
        return (1 - math.exp(-self.num_hashes * n / self.num_bits)) ** self.num_hashes

    def to_bytes(self):
        return bytes(self._bytes)

    @classmethod
    def from_bytes(cls, num_bits, num_hashes, data):
        if len(data) != (num_bits + 7) // 8:
            raise ValueError("bit array length does not match num_bits")
        filt = cls(num_bits, num_hashes)
        filt._bytes = bytearray(data)
        return filt


def build_filter(words, fp_rate=DEFAULT_FP_RATE):
    """Size a filter from the distinct words, then insert them."""
    distinct = []
    seen = set()
    for word in words:
        word = _normalize(word)
        if word and word not in seen:
            seen.add(word)
            distinct.append(word)
    num_bits, num_hashes = optimal_parameters(len(distinct), fp_rate)
    filt = BloomFilter(num_bits, num_hashes)
    for word in distinct:
        filt.add(word)
    return filt


def load_dictionary(path):
    """Read a dictionary file: lowercased, blank lines skipped,
    duplicates collapsed, first-appearance order kept."""
    words = []
    seen = set()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            word = _normalize(line)
            if word and word not in seen:
                seen.add(word)
                words.append(word)
    return words


def save_filter(filt, path):
    header = (
        MAGIC
        + VERSION.to_bytes(2, "big")
        + filt.num_hashes.to_bytes(2, "big")
        + filt.num_bits.to_bytes(4, "big")
    )
    with open(path, "wb") as f:
        f.write(header)
        f.write(filt.to_bytes())


def load_filter(path):
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < HEADER_SIZE:
        raise ValueError(f"{path}: file too short for a CCBF header")
    if data[:4] != MAGIC:
        raise ValueError(f"{path}: bad magic, not a CCBF file")
    version = int.from_bytes(data[4:6], "big")
    if version != VERSION:
        raise ValueError(f"{path}: unsupported version {version}")
    num_hashes = int.from_bytes(data[6:8], "big")
    num_bits = int.from_bytes(data[8:12], "big")
    if num_hashes <= 0:
        raise ValueError(f"{path}: hash count must be positive")
    if num_bits <= 0:
        raise ValueError(f"{path}: bit count must be positive")
    bit_array = data[HEADER_SIZE:]
    if len(bit_array) != (num_bits + 7) // 8:
        raise ValueError(
            f"{path}: bit array is {len(bit_array)} bytes, "
            f"expected {(num_bits + 7) // 8} for {num_bits} bits"
        )
    return BloomFilter.from_bytes(num_bits, num_hashes, bit_array)


def check_words(filt, words):
    """Words probably spelt wrong, in input order, duplicates kept."""
    return [word for word in words if word not in filt]


def _build(argv):
    # argv: dict_path [output] [-o output] [--fp-rate p]
    fp_rate = DEFAULT_FP_RATE
    output = None
    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "-o" and i + 1 < len(argv):
            output = argv[i + 1]
            i += 2
        elif arg == "--fp-rate" and i + 1 < len(argv):
            try:
                fp_rate = float(argv[i + 1])
            except ValueError:
                print(f"error: bad --fp-rate: {argv[i + 1]}", file=sys.stderr)
                return 2
            i += 2
        elif arg.startswith("-"):
            print(f"error: unknown option: {arg}", file=sys.stderr)
            return 2
        else:
            positional.append(arg)
            i += 1
    if not positional:
        print("usage: spell_checker.py -build dict.txt [words.bf]",
              file=sys.stderr)
        return 2
    dict_path = positional[0]
    if output is None:
        output = positional[1] if len(positional) > 1 else DEFAULT_OUTPUT
    if len(positional) > 2:
        print("error: too many arguments to -build", file=sys.stderr)
        return 2
    if not os.path.exists(dict_path):
        print(f"error: dictionary not found: {dict_path}", file=sys.stderr)
        return 1
    try:
        words = load_dictionary(dict_path)
        filt = build_filter(words, fp_rate)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    save_filter(filt, output)
    print(f"{len(words)} words, {filt.num_bits} bits, "
          f"{filt.num_hashes} hash functions -> {output}")
    return 0


def _check(argv):
    filt_path, words = argv[0], argv[1:]
    if not os.path.exists(filt_path):
        print(f"error: filter file not found: {filt_path}", file=sys.stderr)
        return 1
    try:
        filt = load_filter(filt_path)
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    wrong = check_words(filt, words)
    if wrong:
        print("These words are spelt wrong:")
        for word in wrong:
            print(f" {word}")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: spell_checker.py -build dict.txt [words.bf]\n"
              "       spell_checker.py words.bf word1 word2 ...",
              file=sys.stderr)
        return 2
    if argv[0] == "-build":
        return _build(argv[1:])
    if len(argv) >= 2 and argv[0].endswith(".bf"):
        return _check(argv)
    print("usage: spell_checker.py -build dict.txt [words.bf]\n"
          "       spell_checker.py words.bf word1 word2 ...",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
