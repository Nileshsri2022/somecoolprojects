# DESIGN — Spelling Correction Tool

## Assumptions (stated before coding, ponytail rules)

1. This is the companion to entry 41, the Bloom-filter spell
   checker (`spell-checker-bloom/`). That project deliberately
   stores no words and therefore cannot suggest corrections.
   This one MUST store the word list (as a frequency table),
   because suggesting a correction is exactly "find a stored
   word one or two edits away". There is no Bloom filter here.
2. Words are case-insensitive and lowercase-`a-z` only for
   edit generation. Dictionary words and inputs are lowercased
   on entry; `correct_text` restores an initial capital if the
   original word had one. Accented characters, digits and
   apostrophes are not edited: a word containing them is
   treated as-is (it can still match the table exactly, but
   no edit candidates are generated for it). Adding a wider
   alphabet would be speculative surface for this challenge.
3. Frequencies are integers. A bare dictionary word means 1.
   Duplicate lines add frequencies — this matches "how often
   the word occurs in a large body of text" better than
   last-one-wins.
4. One file, Python 3 standard library only, no downloads.
   The Kaggle dataset from Step Zero is NOT bundled or
   downloaded; tests use small synthetic dictionaries.
5. Ranking is exactly the page's rule, made deterministic:
   lowest Levenshtein distance first, then highest frequency,
   then alphabetical order for ties. The page only specifies
   the first two; without the third, equal-frequency
   suggestions would depend on set iteration order and tests
   could not pin the output.

## Algorithm (Norvig-style, as the page describes)

```
correct(word):
    if word in freq: return word
    d1 = known(edits1(word))
    if d1: return best(d1)
    d2 = known(edits1(e) for e in edits1(word))
    if d2: return best(d2)
    return word
```

`suggest()` returns the same ranking as a list instead of a
single winner: the candidates at the lowest available distance
(distance 1 if any exist, otherwise distance 2), ranked
frequency-descending, alphabetical on ties. Distance-2
candidates are never mixed into a distance-1 result — the
page's "lowest distance wins" rule applies to the whole
suggestion list, not just the single best correction.
`correct()` is `suggest(...)[0]` with the word itself as
fallback — one code path, not two.

### Edit generation (Step 3, page-exact)

For a word of length `n`, with splits `(word[:i], word[i:])`
for `i` in `0..n`:

- deletion: `left + right[1:]` for each split with a right part
- transposition: `left + right[1] + right[0] + right[2:]`
  for each split with at least two right characters
- replacement: `left + c + right[1:]` for each `c` in `a-z`
- insertion: `left + c + right` for each `c` in `a-z`

### Bonus exercise (Step 3): how many distance-1 words?

For a word of length `n` over a 26-letter alphabet:

- deletions: `n`
- transpositions: `n - 1`
- replacements: `26n`
- insertions: `26(n + 1)`

Total `= n + (n - 1) + 26n + 26n + 26 = 54n + 25`, i.e.
O(n) candidates (O(1) alphabet). Note the raw count includes
duplicates (e.g. replacing a letter with itself reproduces
the word) and non-words; the implementation deduplicates
with a set and then filters by the dictionary, so the
dictionary check — not generation — is the useful work.

### Distance 2 (Step 4)

Distance-2 candidates are generated only when distance 1
yields nothing, so the common case never pays the
O(n^2)-ish expansion. This is also why the page's rule
"lowest distance wins" holds even against a very frequent
distance-2 word: the distance-2 set is never consulted when
distance 1 succeeds. For a small synthetic dictionary this
is fast; for a full Kaggle-sized table it is the known
expensive step of this approach, and the page's own Going
Further (Bloom filter / trigrams) is the honest answer to
scaling it — not implemented here.

## Text correction

`correct_text` tokenises with a regex over runs of ASCII
letters (`[A-Za-z]+`); everything else (spaces, punctuation,
digits) passes through untouched, and word positions are
preserved. Capitalisation: if the original token starts with
an uppercase letter and the rest is lowercase, the correction
is capitalised the same way; all-caps and mixed-case tokens
are left lowercase-corrected except for that first-letter
rule — deliberately minimal, not a case model.

## CLI shape (and what was NOT added)

- The dictionary is the first positional argument, then the
  words — mirroring the page's `./ccspell <words...>` shape
  with the dictionary made explicit (the page never names a
  dictionary argument; a tool that silently baked in a
  dictionary path would be untestable, so the path is an
  argument).
- `--time` is opt-in, not default: the page presents timing
  as the optional Step 5, so default output is just the
  `input correction` pairs. With `--time`, the timing line
  uses the page's exact format, with milliseconds to six
  decimal places as in the example (`20.026833ms`).
- No stdin mode: with no words and no `--correct`/`--file`,
  the program reports a usage error instead of blocking on
  stdin. This avoids the classic "it hung" failure when a
  user runs it with no arguments.
- No `--suggestions` + `--correct` combination: suggestions
  are a word-mode feature; combining them with whole-text
  correction would need an output format the page does not
  define, so it is a usage error.

## Success criteria (verifiable)

- Every Step 3 edit type produces a known correction in
  tests (deletion, insertion, transposition, replacement).
- Frequency ranking, distance preference, and the
  alphabetical tie-break are each pinned by a test.
- CLI word mode, `--correct`, `--file`, `--suggestions`,
  and `--time` are covered end-to-end in temp directories.
- `python3 -m unittest discover -s tests -v` passes clean.

## Divergences from the page (documented, not hidden)

1. Dictionary file format is defined by this build (the page
   fixes none): `word [frequency]` per line; see SPEC.md.
2. Kaggle dataset not downloaded or bundled; synthetic
   dictionaries only. The loader accepts any real frequency
   list in the documented format.
3. Timing is opt-in via `--time` (page's Step 5 is optional).
4. Alphabetical tie-break added to the page's ranking rule
   for determinism (page specifies distance, then frequency).
5. No Bloom filter, trigram, phonetic, or context support
   (page's Going Further, explicitly out of scope).
