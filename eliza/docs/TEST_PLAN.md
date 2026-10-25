# ELIZA — TEST_PLAN

## How to run

From this directory:

```
python3 -m unittest discover -s tests -v
```

or:

```
python3 tests/test_eliza.py
```

Python 3.8+ standard library only. No network, no fixtures beyond a
small inline script dict and a temporary script file created by the
tests themselves (in `tempfile`, cleaned up by the test).

## Coverage map (each area has at least one test)

| Area | What is asserted |
|---|---|
| Quit detection | `quit`, `goodbye`, `bye` quit (case-insensitive, punctuation-tolerant); `exit`, `bye for now`, empty string, and `goodbyes` do NOT quit |
| Tokenisation | lower-casing, apostrophe removal (`don't` → `dont`), punctuation as separator |
| Reflection | every table entry (i/you, my/your, me/you, am/are, …), unknown words unchanged |
| Decomposition matching | literal-only match; leading/trailing `0` wildcards; middle wildcard; empty wildcard capture; non-match when words are left over or a literal differs |
| Reassembly numbering | page's WHY example: component `5` is the trailing wildcard; reflected insertion (`my` → `your`) |
| WHY rule end-to-end | all four reassemblies in cycle order for "Why don't I try harder?" |
| Keyword priority | input matching two keywords answers with the earlier-in-file rule; script order, not input order, decides |
| Redirection | a `=WHAT` reassembly delegates to the WHAT rule's reply |
| Hello / Step 2 example | "hello" → "Hello, how are you feeling today?" |
| Fallback | no-keyword input cycles fallbacks, starting with "I see." |
| Memory | a memory-marked rule queues its reply; a later no-keyword input replays it before any fallback; replay consumes it; queue capacity drops the oldest |
| Script loading | the shipped `doctor.json` loads and contains the WHY rule; a temp script file loads and drives replies; missing file and malformed JSON raise |
| Scripted exchanges | multi-turn conversations through `Eliza.reply` (greeting → feeling → WHY → fallback), exact strings |
| REPL (subprocess) | piped stdin `hello` then `quit` prints banner, greeting, hello reply, goodbye line, exits 0; EOF-only stdin exits 0 with goodbye line; `--help` exits 0 |
| Determinism | two fresh engines fed the same inputs produce identical replies |

## What is NOT tested (honestly)

- The historical accuracy of the script against Weizenbaum's original
  DOCTOR script — the script here is original (see SPEC.md divergence 2),
  so there is no gold transcript to diff against.
- Any therapeutic quality or "human-likeness" — not measurable, not
  claimed.
- Interactive terminal behaviour (arrow keys, line editing) — stdin is
  read with plain `input()`; the subprocess tests cover piped stdin only.
