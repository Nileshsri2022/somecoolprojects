# loc-counter — Build Your Own LOC Counter

Coding Challenges: Build Your Own LOC Counter
(https://codingchallenges.fyi/challenges/challenge-loc-counter/),
worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Walks a directory tree and counts blank, comment, and code
lines per file and in total, grouped by language — a small
local version of `cloc` / `scc`.

## Usage

```sh
python3 loc.py <directory>          # per-language summary (default)
python3 loc.py --files <directory>  # per-file breakdown
python3 loc.py --json <directory>   # JSON output (files + languages + total)
```

A single file path is also accepted in place of a directory.
Unknown extensions are skipped; hidden files and directories
(such as `.git`) are skipped; binary files are skipped.

Languages are one table row each in `loc.py` (`LANGUAGES`):
Python, C, C Header, C++, Java, JavaScript, TypeScript, Go,
Rust, Shell, Ruby, Markdown (fenced code blocks), and Text
(blank vs non-blank only). A line counts once: as code if it
contains any code outside comments, otherwise as a comment —
so the page's Step 4 example, `i++; /*` / `comment` / `*/`,
counts as 1 code + 2 comment lines.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use temp-directory fixtures with hand-computed counts
(never the somecoolprojects tree itself) and cover Python
and C-like comment rules, the Step 4 block-comment case,
Markdown fences, plain text, recursive walking with
per-language totals, and all three CLI output modes.

## Files

- `loc.py` — language table, line scanner, walker, CLI.
- `docs/SPEC.md` — challenge spec and supported languages.
- `docs/DESIGN.md` — pipeline, classification rules, assumptions.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_loc.py` — the test suite.
