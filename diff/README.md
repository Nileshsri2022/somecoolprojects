# diff — Build Your Own diff Tool

Coding Challenges #13, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Compares two files line by line (longest common subsequence)
and prints only the changed lines: `< ` for lines only in the
first file, `> ` for lines only in the second file. Identical
files print nothing.

## Usage

```sh
python3 diff.py orig.txt new.txt
```

Example (the challenge page's paragraph case):

```
< Coding Challenges helps you become a better software engineer through that build real applications.
> Helping you become a better software engineer through coding challenges that build real applications.
< I’ve used or am using these coding challenges as exercises to learn a new programming language or technology.
> These are challenges that I’ve used or am using as exercises to learn a new programming language or technology.
```

Exit status is `0` whether the files are identical or
different, `2` for the wrong number of arguments, `1` for an
unreadable file. This is not GNU diff: no hunk headers, line
numbers, `---` separators, context, or options — the output
format is exactly the one the challenge page specifies.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover the page's Step 1/2/3 cases verbatim, diff
reconstruction, `difflib` as a test-only oracle, comparison
against system `diff` on unambiguous fixtures, and CLI
argument/file-error cases.

## Files

- `diff.py` — LCS, diff generation, CLI (stdlib only).
- `docs/SPEC.md` — challenge spec and CLI contract.
- `docs/DESIGN.md` — algorithm choice (DP LCS + prefix/suffix
  trim) and deliberate divergences from GNU diff.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_diff.py` — the test suite.
