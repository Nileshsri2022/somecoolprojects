# ELIZA — a rule-based chatbot (not an LLM)

A version of Joseph Weizenbaum's ELIZA (MIT, 1964–1967) built for
[Coding Challenge #89 — Build Your Own ELIZA](https://codingchallenges.fyi/challenges/challenge-eliza/).

**Responses are scripted rules, not intelligence.** The program finds a
keyword in your input, splits the input with a decomposition pattern, and
rebuilds the parts (with pronoun reflection, e.g. my → your) into a reply
from a script file. If no rule matches, it replays a stored memory reply
or falls back to a context-free line such as "I see." Nothing here learns,
understands, or calls a language model.

## Run

Python 3 standard library only — no packages to install:

```
python3 eliza.py
```

```
ELIZA -- a rule-based chatbot (not an AI, not a language model).
...
> hello
Hello, how are you feeling today?
> why don't i try harder?
Do you believe I don't try harder?
> quit
Goodbye. Thank you for talking to me.
```

Quit with `quit`, `goodbye`, or `bye` (whole input, case-insensitive).
Use `--script PATH` to load a different JSON rule script.

## Files

- `eliza.py` — the whole program (REPL + engine + script loader).
- `doctor.json` — the DOCTOR-style rule script, loaded from file at
  start-up. An original script in the style of Weizenbaum's, not a verbatim
  copy of the historical script (see `docs/SPEC.md`).
- `docs/SPEC.md` — challenge steps, divergences, scope limits.
- `docs/DESIGN.md` — engine design and the JSON script format.
- `docs/TEST_PLAN.md` — what the tests cover.
- `tests/test_eliza.py` — unittest suite.

## Tests

```
python3 -m unittest discover -s tests -v
```
