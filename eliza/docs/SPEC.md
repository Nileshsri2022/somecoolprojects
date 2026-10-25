# ELIZA — SPEC

## Challenge (resolved page)

- Challenge page (read in full before writing anything):
  <https://codingchallenges.fyi/challenges/challenge-eliza/>
- Mirror / original post (Coding Challenge #89, published 2025-05-10):
  <https://codingchallenges.substack.com/p/coding-challenge-89-eliza>
- Tags on codingchallenges.fyi: ai, artificial intelligence, machine learning, cli.
- Author: John Crickett, Coding Challenges. The challenge builds a version of
  Joseph Weizenbaum's ELIZA (MIT, 1964–1967), whose DOCTOR script mimicked a
  Rogerian psychotherapist.

## Honest statement about what this is

ELIZA is **rule-based pattern matching and substitution, not intelligence,
not learning, and not an LLM**. Nothing in this project calls, trains, or
emulates a language model. Every reply is produced by a scripted rule:
a keyword is found in the input, a decomposition pattern splits the input
into parts, and a reassembly template rebuilds those parts (with pronoun
reflection) into a reply. If no rule matches, a context-free fallback reply
is used. Responses that look understanding are an illusion — the
"ELIZA effect" the challenge page itself describes.

## Challenge steps and how each is met

### Step 0 — Set up

Python 3 standard library only. No third-party packages, no network, no
model downloads. Run: `python3 eliza.py` from this directory.

### Step 1 — Welcome banner, prompt, quit

- On start the program prints a welcome banner and repeatedly prompts with
  `> `.
- The user quits by typing, case-insensitively and ignoring surrounding
  punctuation/whitespace, exactly one of: `quit`, `goodbye`, `bye`.
  On quitting it prints a goodbye line and exits 0.
- End-of-input (Ctrl-D / closed stdin) also ends the conversation cleanly
  with the goodbye line, exit 0.
- An empty line re-prompts without producing a reply.

### Step 2 — Match input to a response pattern

- Patterns live in a data structure, not hard-coded in the matching code:
  the script file `doctor.json` holds a list of keyword rules, each with
  decomposition patterns and reassembly templates.
- Example from the page: input matching `/^hello(.*)/gi` is answered with
  "Hello, how are you feeling today?" — implemented as the HELLO keyword
  rule (first decomposition matches any input containing `hello`).
- Step 1's "print the input back" behaviour is superseded by Step 2, as the
  page intends (echo mode is not kept as a mode).

### Step 3 — Load the rules from a file

- Rules are loaded at start-up from `doctor.json` (same directory as
  `eliza.py` by default; `--script PATH` overrides it).
- The page's worked example is implemented verbatim in spirit as the WHY
  rule: keyword `WHY`, decomposition `(0 WHY DON'T I 0)`, reassemblies
  "Do you believe I don't …?", "Perhaps I will … in good time.",
  "Should you … yourself?", "You want me to …?", plus the `=WHAT`
  fallback rule. See DESIGN.md for how the numbering works.
- If the script file is missing or invalid JSON, the program prints an
  error to stderr and exits non-zero instead of silently falling back to
  built-in rules. There is no hidden built-in script.

### Step 4 — Keyword priority, decomposition, reassembly

- Keywords are whole words in the input. If several keywords match, the
  one earliest in the script file wins (the page: "Priority is defined by
  the order of the rules in the input file, from highest to lowest") —
  with one refinement: if that keyword's decompositions all fail to fit
  the sentence, the next matching keyword is tried, so an ill-fitting
  high-priority keyword does not block a fitting lower-priority one.
- Within a keyword, decomposition patterns are tried in file order; the
  first that matches is used.
- A decomposition is a list of tokens. A token `0` is a wildcard capturing
  any run of words (including an empty run). Any other token must match
  the corresponding input word exactly (after normalisation, below).
- A reassembly is a list of tokens. A numeric token `N` inserts
  decomposition component N (1-based, counting every decomposition token,
  wildcards included — so in `(0 WHY DON'T I 0)`, `5` is the trailing
  wildcard, exactly as in the page's example). Non-numeric tokens are
  literal words. Captured wildcard text is pronoun-reflected before
  insertion (see DESIGN.md).
- A reassembly consisting of a single token `=OTHER` delegates to the
  rules of keyword `OTHER` (the page's `=WHAT` fallback). Delegation is
  capped (10 hops) to avoid infinite loops; a loop or unknown target
  falls through to the no-keyword fallback.
- Successive replies from the same decomposition cycle through its
  reassemblies in file order, one per use, wrapping around. This is
  deterministic (not random), so conversations and tests are reproducible.
  The original ELIZA cycled similarly; the page does not mandate random
  choice, and determinism is a deliberate, documented choice.

### Step 5 — Edge cases: no keyword matches

- If no keyword matches, the program first recalls a stored memory reply
  if one is queued (see DESIGN.md), otherwise it cycles through the
  context-free fallback list from the script file, which includes "I see."
  exactly as the page suggests, plus "Please go on.", "Tell me more about
  that.", and similar.
- Input with no words at all (only punctuation) is treated like an empty
  line: it re-prompts, because there is nothing to match on.

### Going Further — NOT built

- No custom script editor, no web deployment, no sharing/publishing step,
  no user-defined scripts beyond editing `doctor.json` by hand (which is
  supported: the format is documented in DESIGN.md, and any JSON file in
  the same shape works with `--script`).
- No voice, GUI, network server, or persistence of conversations across
  runs. Memory lives only for the duration of one session.

## Input normalisation (documented, applies to matching only)

- Lower-cased for matching; apostrophes are removed (`don't` → `dont`,
  so the script writes `dont`, matching the page's `DON'T`).
- Punctuation other than apostrophes is treated as a word separator.
- Output is sentence-cased: first letter capitalised, trailing `.`/`?`
  from the template kept, otherwise a `.` is appended. Reflected fragments
  keep the user's words apart from pronoun swaps.

## Pronoun reflection (substitution table)

Applied to captured wildcard text only, word by word, before insertion:

| user word | becomes | | user word | becomes |
|---|---|---|---|---|
| i | you | | you | i |
| me | you | | your | my |
| my | your | | yours | mine |
| am | are | | are | am |
| myself | yourself | | yourself | myself |
| mine | yours | | we | you |
| us | you | | our | your |

Words not in the table pass through unchanged. Reflection is deliberately
naive (no grammar, no verb agreement beyond am/are) — that naivety is part
of the original design and is not hidden.

## Deliberate divergences from the page / original ELIZA

1. **Script format is JSON, not the original Lisp S-expressions.**
   The page shows the DOCTOR script in Lisp-like form but does not mandate
   that format; JSON is parseable with the Python standard library alone
   and keeps "load the rules from a file" honest without writing a Lisp
   parser. The semantics (keyword / decomposition / reassembly / `=KEY`
   redirection) are preserved.
2. **The script is an original DOCTOR-style script, not a verbatim copy
   of Weizenbaum's DOCTOR script.** It is inspired by it and covers the
   same therapist-style ground (feelings, family, wants, memories, dreams),
   and it includes the page's WHY example. It is not claimed to be the
   historical script; the page links to that script for reference but does
   not require reproducing it word for word.
3. **Deterministic reassembly cycling instead of random choice.**
   See Step 4 above. The page never specifies random selection.
4. **Memory is a small FIFO queue (capacity 5, oldest dropped).**
   The parent task brief asked for memory; the page itself only sketches
   fallback behaviour. Memory rules are marked `"memory": true` in the
   script; when such a rule fires, its reply is also queued, and a queued
   memory reply is used before the generic fallback when a later input
   matches no keyword. This is an addition beyond the page's steps,
   documented here rather than presented as page-mandated.
5. **Quit words are matched as the whole input only.** Typing "bye" inside
   a longer sentence ("bye for now, I must go") does NOT quit; it is
   answered by the normal rules (BYE is not a keyword rule, so it falls
   back). The page says "type a response that would end the conversation,
   for example: quit, goodbye, or bye" — whole-input matching is the
   least surprising reading.
6. **No `exit` quit word.** Only the page's three words quit the program.
   (Typing `exit` is answered by the fallback rules.)
7. **Keyword matching is whole-word only.** "Why" inside "whyever" does
   not trigger WHY. This follows the page's "keywords are words matched
   in the rules".

## What is NOT built / NOT claimed

- No intelligence, understanding, learning, memory across sessions,
  sentiment analysis, or language-model behaviour of any kind.
- No verbatim historical DOCTOR script (see divergence 2).
- No Lisp script parser, no script editor, no web UI, no conversation
  logging to disk.
- No claim that replies are appropriate therapeutic advice: this is a
  historical pattern-matching demo. The banner says so in one line.

## Files

- `eliza.py` — the whole program (REPL + engine + script loader).
- `doctor.json` — the rule script loaded from file.
- `docs/SPEC.md` (this file), `docs/DESIGN.md`, `docs/TEST_PLAN.md`.
- `tests/test_eliza.py` — unittest suite (see TEST_PLAN.md).
- `README.md` — user-facing usage summary.
