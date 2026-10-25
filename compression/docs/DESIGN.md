# compression — Design

## Assumptions (stated before coding, per ponytail)

1. Language: Python 3, standard library only, single file
   `huffman.py`, same as `ccwc.py` and `json_parser.py` in
   this repo. Reason: consistency, no build step, challenge
   allows any language.
2. Symbols are bytes (0-255), not characters. Reason: the
   challenge says "text files", but byte symbols handle any
   file, including UTF-8 text, without a text-decoding step,
   and the frequency table then has at most 256 entries.
3. The header carries frequencies, not the tree. Reason: it
   is the simpler of the two options the challenge allows,
   and with deterministic tie-breaking the decoder rebuilds
   the exact same tree. No tree serialisation code is needed.
4. Ask-matt / ponytail skill files: same status as for the
   previous projects — ask-matt install was still running
   with no output, ponytail was never confirmed installed.
   The ponytail behavioural guidelines recorded in memory
   are applied anyway.

## Algorithm

### 1. Frequencies

One pass over the input bytes, counting with a dict
(or `collections.Counter`). O(n) time, O(256) distinct symbols.

### 2. Tree building (Huffman, greedy)

Use a min-heap of nodes, ordered by (frequency, insertion
order). Insertion order is a counter that increases for every
node pushed, so ties are broken deterministically and the
encoder and decoder — both starting from symbols sorted by
byte value — build the same tree.

```
heap = [(freq, order, Leaf(symbol)) for symbol, freq in
        sorted(frequencies.items())]
while len(heap) > 1:
    f1, _, n1 = heappop(heap)
    f2, _, n2 = heappop(heap)
    heappush(heap, (f1 + f2, next_order,
                    Internal(n1, n2)))
root = heap[0].node
```

This is the classic Huffman construction: repeatedly merge
the two lowest-frequency nodes. The result is an optimal
prefix code (for this symbol set) in the sense that no other
prefix code has a smaller weighted path length.

### 3. Code table

Walk the tree from the root: left edge appends `0`, right
edge appends `1`. A leaf's path is its code. By construction
no code is a prefix of another (each code ends at a leaf,
and leaves have no children).

Special case — one distinct symbol: the tree is a single
leaf with no edges, so its path would be empty, and an empty
code cannot be written or read. Define its code as `"0"`.
The decoder handles this case separately: with a single-leaf
tree, each input bit produces that symbol (the bit value is
ignored, only its presence counts).

### 4. Encoding (bit packing)

```
writer = BitWriter()
for byte in input:
    writer.write(code_table[byte])   # string of '0'/'1'
output = header + writer.flush()     # pad last byte with 0s
```

Bits are packed MSB-first: the first code bit goes into the
most significant bit of the first output byte. `BitWriter`
accumulates bits in an integer buffer and emits full bytes.

### 5. Decoding

```
root = build_tree(frequencies)
if root is a leaf:  # single-symbol case
    output = bytes([symbol]) * total_symbols
else:
    node = root
    for bit in BitReader(bitstream):
        node = node.left if bit == 0 else node.right
        if node is a leaf:
            output.append(node.symbol); node = root
            if len(output) == total_symbols: stop
```

If the bitstream ends before `total_symbols` symbols have
been produced, the input is truncated — raise an error,
do not return a short output.

## File layout

```
compression/
  README.md            usage, examples, how to run tests
  huffman.py           frequencies, tree, codes, format, CLI
  docs/
    SPEC.md            challenge spec and file format
    DESIGN.md          this file
    TEST_PLAN.md       what is tested, and against what
  tests/
    test_huffman.py    unittest, functions + CLI subprocess
```

## Success criteria

- `python3 -m unittest discover -s tests -v` passes.
- Roundtrip is byte-identical for: empty, single symbol,
  `aaabbc`, all 256 byte values, repetitive text, and a
  larger repetitive text where compressed < original.
- Codes are prefix-free, and a more frequent symbol never
  gets a longer code than a less frequent one in the test
  cases (checked via the code table, not just roundtrip).
- Corrupt inputs (bad magic, truncated header, truncated
  bitstream) fail with a non-zero exit, not a silent output.
