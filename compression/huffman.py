#!/usr/bin/env python3
"""compression - Build Your Own Compression Tool (Coding Challenges #3).

Usage:
  huffman.py compress <input> <output>
  huffman.py decompress <input> <output>

Huffman coding over bytes. Format (see docs/SPEC.md):
  "CHUF", distinct count (uint32 BE), then per symbol in
  ascending byte order: 1-byte symbol + frequency (uint32 BE),
  then the bitstream, codes packed MSB-first, padded with 0s.

Python standard library only, single file.
"""

import heapq
import itertools
import struct
import sys
from collections import Counter

MAGIC = b"CHUF"


class HuffmanError(Exception):
    pass


class Leaf:
    __slots__ = ("symbol",)

    def __init__(self, symbol):
        self.symbol = symbol


class Internal:
    __slots__ = ("left", "right")

    def __init__(self, left, right):
        self.left = left
        self.right = right


def frequencies(data):
    """Return {byte: count} for data. Challenge step 1."""
    return dict(Counter(data))


def build_tree(freq):
    """Build a Huffman tree. Deterministic tie-breaking: symbols
    are inserted in ascending byte order, and the heap breaks
    frequency ties by insertion order, so encoder and decoder
    build the same tree from the same frequency table."""
    if not freq:
        return None
    counter = itertools.count()
    heap = []
    for symbol, count in sorted(freq.items()):
        heapq.heappush(heap, (count, next(counter), Leaf(symbol)))
    while len(heap) > 1:
        f1, _, n1 = heapq.heappop(heap)
        f2, _, n2 = heapq.heappop(heap)
        heapq.heappush(heap, (f1 + f2, next(counter), Internal(n1, n2)))
    return heap[0][2]


def build_codes(root):
    """Return {byte: bitstring}. Prefix-free by construction:
    each code ends at a leaf. Single-symbol tree gets code "0",
    since an empty code cannot be written or read."""
    if root is None:
        return {}
    if isinstance(root, Leaf):
        return {root.symbol: "0"}
    codes = {}

    def walk(node, prefix):
        if isinstance(node, Leaf):
            codes[node.symbol] = prefix
        else:
            walk(node.left, prefix + "0")
            walk(node.right, prefix + "1")

    walk(root, "")
    return codes


class BitWriter:
    def __init__(self):
        self.bytes = bytearray()
        self.current = 0
        self.filled = 0

    def write(self, bits):
        for bit in bits:
            self.current = (self.current << 1) | (bit == "1")
            self.filled += 1
            if self.filled == 8:
                self.bytes.append(self.current)
                self.current = 0
                self.filled = 0

    def flush(self):
        if self.filled:
            self.bytes.append(self.current << (8 - self.filled))
            self.current = 0
            self.filled = 0
        return bytes(self.bytes)


class BitReader:
    def __init__(self, data):
        self.data = data
        self.pos = 0  # bit position

    def read_bit(self):
        if self.pos >= len(self.data) * 8:
            return None
        byte = self.data[self.pos // 8]
        bit = (byte >> (7 - (self.pos % 8))) & 1
        self.pos += 1
        return bit


def compress(data):
    """Encode bytes to the CHUF format."""
    freq = frequencies(data)
    root = build_tree(freq)
    codes = build_codes(root)
    header = bytearray(MAGIC)
    header += struct.pack(">I", len(freq))
    for symbol in sorted(freq):
        header += struct.pack(">BI", symbol, freq[symbol])
    writer = BitWriter()
    for byte in data:
        writer.write(codes[byte])
    return bytes(header) + writer.flush()


def decompress(data):
    """Decode CHUF format back to the original bytes."""
    if len(data) < 8 or data[:4] != MAGIC:
        raise HuffmanError("bad magic: not a CHUF file")
    (distinct,) = struct.unpack(">I", data[4:8])
    if distinct > 256:
        raise HuffmanError(f"invalid distinct symbol count {distinct}")
    header_size = 8 + 5 * distinct
    if len(data) < header_size:
        raise HuffmanError("truncated header")
    freq = {}
    offset = 8
    for _ in range(distinct):
        symbol, count = struct.unpack(">BI", data[offset:offset + 5])
        if symbol in freq:
            raise HuffmanError(f"duplicate symbol {symbol} in header")
        freq[symbol] = count
        offset += 5
    total = sum(freq.values())
    if total == 0:
        return b""
    root = build_tree(freq)
    if isinstance(root, Leaf):
        # Single-symbol case: each bit is one symbol (see DESIGN.md).
        bits_available = (len(data) - header_size) * 8
        if bits_available < total:
            raise HuffmanError("truncated bitstream")
        return bytes([root.symbol]) * total
    out = bytearray()
    reader = BitReader(data[header_size:])
    node = root
    while len(out) < total:
        bit = reader.read_bit()
        if bit is None:
            raise HuffmanError("truncated bitstream")
        node = node.left if bit == 0 else node.right
        if isinstance(node, Leaf):
            out.append(node.symbol)
            node = root
    return bytes(out)


def main(argv):
    if len(argv) != 3 or argv[0] not in ("compress", "decompress"):
        print("usage: huffman.py compress <input> <output>\n"
              "       huffman.py decompress <input> <output>",
              file=sys.stderr)
        return 2
    command, in_path, out_path = argv
    try:
        with open(in_path, "rb") as f:
            data = f.read()
    except OSError as exc:
        print(f"huffman: {in_path}: {exc.strerror}", file=sys.stderr)
        return 1
    try:
        result = compress(data) if command == "compress" else decompress(data)
    except HuffmanError as exc:
        print(f"huffman: {exc}", file=sys.stderr)
        return 1
    try:
        with open(out_path, "wb") as f:
            f.write(result)
    except OSError as exc:
        print(f"huffman: {out_path}: {exc.strerror}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
