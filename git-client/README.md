# git-client — Build Your Own Git

Coding Challenges #27, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A minimal git client in one Python-stdlib file. It reads and
writes a real `.git` directory layout, so real git can verify
its work (`git status`, `git log`, `git ls-tree` all read repos
it creates). Core logic never shells out to system git; git is
used only as a test oracle.

## Usage

```sh
python3 git_client.py init demo
cd demo
echo "Hello CC" > hello-coding-challenges.txt
python3 ../git_client.py add hello-coding-challenges.txt
python3 ../git_client.py status
python3 ../git_client.py commit "Add Hello CC"
python3 ../git_client.py log
echo "Hello Diff Step" >> hello-coding-challenges.txt
python3 ../git_client.py diff
```

Commands: `init [dir]`, `add <path>...`, `status`,
`commit [-m] <message>`, `log`, `hash-object [-w] <file>`,
`cat-file -p|-t|-s <sha>`, `diff [--cached]`,
`checkout -- <path>`, `checkout <commit-ish>`.
`push` is accepted only to report that it is not implemented
(see below).

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

21 tests, all in temp directories: init layout, hash-object
(known SHA + git oracle), index contents, status sections,
commit/parent/log, cat-file, diff, checkout, and the push stub.
Oracle assertions run wherever `git` is on PATH.

## Files

- `git_client.py` — the whole client: objects, index v2, trees,
  commits, status, diff, checkout.
- `docs/SPEC.md` — the challenge steps as implemented.
- `docs/DESIGN.md` — assumptions and documented divergences.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_git_client.py` — the test suite.

## Divergence (honest)

Step 6 of the challenge — pushing to GitHub over HTTPS with a
personal access token via the smart-HTTP protocol — is NOT
implemented. It needs network access and a real account/token,
which an offline build must not invent, and a half-built push
that claims success would be faking the step. `push` exits
non-zero with that explanation. Steps 1–5 are fully implemented.
