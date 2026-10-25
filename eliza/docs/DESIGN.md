# ELIZA — DESIGN

## Architecture (one file, stdlib only)

```
doctor.json ──load──> script dict ──> Eliza engine ──> reply string
   (data)                (rules)         (pure functions)     |
                                                      REPL (stdin/stdout)
```

`eliza.py` contains, in order:

1. `REFLECTIONS` — the pronoun-swap table (see SPEC.md).
2. `load_script(path)` — reads JSON, validates its shape, raises
   `ValueError` with a clear message on any structural problem.
3. Normalisation: `tokenize(text)` — lower-case, drop apostrophes,
   replace every other non-alphanumeric character with a space, split.
4. Reflection: `reflect(words)` — word-by-word table lookup.
5. Decomposition matching: `match_decomposition(pattern, words)` —
   token-by-token with `0` wildcards. Returns the list of components
   (one entry per pattern token; a wildcard component is the list of
   words it captured, a literal component is that one word) or `None`.
   Matching is greedy-left-to-right with backtracking: a wildcard takes
   the fewest words that still lets the rest of the pattern match, which
   is what makes `(0 WHY DONT I 0)` split "why dont i try harder" into
   `[] + [try, harder]` as expected.
6. Reassembly: `reassemble(template, components)` — numeric tokens pick
   a component (1-based); captured words are reflected; literal tokens
   are used as-is. A template of exactly `["=KEY"]` is a redirection,
   handled by the caller, not here.
7. `Eliza` class — holds the script, per-decomposition reply counters,
   the memory queue, and the fallback counter. Methods:
   - `reply(text)` — full pipeline, returns a reply string or `None`
     for quit (the REPL checks quit before calling this; `is_quit`
     is a separate function so tests can cover it without I/O).
   - `_find_keyword(words)` — first script rule, in file order, whose
     keyword appears as a whole word in the input.
   - `_apply_keyword(rule, words, depth)` — tries decompositions in
     order; on a match, cycles to the next reassembly, handles `=KEY`
     redirection (depth cap 10), and queues memory replies.
   - `is_quit(text)` — module-level function, whole-input check.
8. `main(argv)` — argument parsing (`--script`, `--help`), banner,
   read-eval-print loop. EOF and KeyboardInterrupt end cleanly.

No other modules are needed; `sys`, `json`, `argparse` (or manual
parsing — argparse is used), and `re` (only for sentence-casing helpers
in output formatting, not for rule matching) are all stdlib.

## Script format (`doctor.json`)

```json
{
  "initial": ["How do you do. Please tell me your problem."],
  "final": ["Goodbye. Thank you for talking to me."],
  "fallbacks": ["I see.", "Please go on.", "..."],
  "memory_capacity": 5,
  "rules": [
    {
      "keyword": "hello",
      "decompositions": [
        {
          "pattern": ["0", "hello", "0"],
          "reassemblies": [["Hello, how are you feeling today?"]],
          "memory": false
        }
      ]
    }
  ]
}
```

Rules:

- `initial`: printed once after the banner, before the first prompt.
  (The page does not mandate an opening line; one is included because
  the historical ELIZA greeted the user, and it is listed here, not
  hidden. It is a single fixed line, not a claim of understanding.)
- `final`: printed on quit / EOF.
- `fallbacks`: context-free replies, cycled in order.
- `memory_capacity`: max queued memory replies (default 5 if absent).
- `rules`: ordered list — **order is priority** (page, Step 4).
- Each rule: `keyword` (single lower-case word, matched whole-word),
  `decompositions` in try order.
- Each decomposition: `pattern` (tokens; `0` = wildcard), `reassemblies`
  (each a token list; numeric tokens are 1-based component references;
  a single `=KEY` token is a redirection), optional `memory` (bool,
  default false). When a memory decomposition fires, the reply it
  produces is appended to the memory queue (dropping the oldest past
  capacity) **in addition** to being returned immediately.
- Reassembly literal tokens are emitted verbatim (they already carry
  their own capitalisation in the file, e.g. "Hello,"); numeric
  components are reflected and lower-cased, then the whole reply is
  sentence-cased (first letter upper, ensure trailing `.` or `?`).

### Worked example — the page's WHY rule

Input: "Why don't I try harder?"
Normalised words: `[why, dont, i, try, harder]`.
Keyword WHY (file order puts WHY before the generic rules that could
also match, e.g. I) → decomposition `["0","why","dont","i","0"]` →
components: `1=[]`, `2=why`, `3=dont`, `4=i`, `5=[try, harder]`.
Reassembly `["Do","you","believe","I","don't","5"]` → the `5` expands
to reflected `[try, harder]` (no pronouns to swap) → "Do you believe
I don't try harder?" (apostrophe in the literal template token
`don't` is kept as written; matching normalisation does not rewrite
output literals). The other three reassemblies cycle on repeat uses,
and a decomposition with only `["=WHAT"]` would delegate to WHAT.

Note on numbering: components are counted over **all** decomposition
tokens, literals included. That is why the trailing wildcard is `5`,
not `2`. This matches the page's example exactly.

## Reply pipeline (exact order)

1. `is_quit`? (REPL only) → print `final`, exit.
2. Tokenize. Zero tokens → no reply (REPL re-prompts).
3. Find keywords present as whole words, in script order.
4. For each such keyword in order: try its decompositions in order;
   first match wins. If a keyword's decompositions all fail, the next
   matching keyword is tried (a keyword whose patterns do not fit the
   sentence does not block a lower-priority keyword that does).
   - If the chosen reassembly is a redirection, apply the target
     keyword's rules (depth ≤ 10, then fallback).
   - Otherwise return the cycled reassembly; queue it too if the
     decomposition is a memory rule.
5. If no keyword, or no decomposition matched: pop the oldest queued
   memory reply if any; else return the next fallback, cycling.
6. Format: join tokens with single spaces, capitalise the first
   letter, ensure a trailing `.` or `?` (templates ending in `!` keep
   it; a template with no terminal punctuation gains `.`).

## Memory semantics

- Memory is recall of the user's own earlier words, not learning: a
  memory reply is a template filled with a fragment the user already
  said, stored verbatim (post-reflection) and replayed once, in FIFO
  order, only when a later input matches no keyword.
- A memory reply is consumed when replayed (it is popped, not kept).
- Queue capacity 5; overflow drops the oldest, silently — documented
  here so the drop is not a surprise.

## Determinism

No `random` module use anywhere. Reassembly and fallback selection are
counters modulo list length, per decomposition / global respectively.
Two identical sessions with identical inputs produce identical outputs,
which is what makes the scripted-exchange tests exact.

## Failure modes

- Missing/unreadable/invalid script → stderr message + exit code 2
  (argparse errors keep their own code 2 as well). No silent fallback
  to built-in rules.
- Unknown `=KEY` target or redirection loop → falls through to the
  memory/fallback path instead of crashing or looping forever.
- A decomposition pattern with no wildcard and extra input words does
  not match (all input words must be consumed by the pattern) — except
  that leading/trailing `0` wildcards absorb the surplus, which is the
  normal shape of the rules in `doctor.json`.
