# Online Python Playground

A local web playground: write Python in the browser, click Run, and see
output or errors immediately. Challenge:
https://codingchallenges.fyi/challenges/challenge-online-python-playground

## Run

```
python3 playground.py            # http://127.0.0.1:8000/
python3 playground.py --port 8765
```

Open the printed URL in a browser. Type code, press **Run** (or
Ctrl/Cmd+Enter). Errors show the error type, message, and line number,
with the full traceback in a collapsible block.

## Features

- Editor with a lightweight self-contained syntax-highlight preview
  (keywords, strings, numbers, comments, builtins), native undo/redo
  and copy/paste, Ctrl+Enter to run, Ctrl+S to save.
- Save / load / delete snippets in the browser's localStorage
  (survives reload; quota errors are shown, not thrown).
- Timeout (default 5 s, `PLAYGROUND_TIMEOUT` env var) + loading
  indicator; long-running code is killed and reported as a timeout.
- Dark-mode toggle (persisted), keyboard-shortcuts guide, and
  share links (`#code=<base64url>` fragment — opening one loads the
  code; nothing is stored server-side).
- No stdin: `input()` raises `EOFError`, shown like any other error.

## ⚠️ Security — local demo sandbox only

This is **not production-grade sandboxing and is not safe for
untrusted users**. Code runs on this machine under best-effort limits
only: a fresh temp directory per run (deleted afterwards), a 5 s
timeout, CPU/memory/file-size/process resource limits, a minimal
environment, and an audit hook blocking network use, subprocesses,
`os.system`/`exec`/`fork`, and file access outside the run directory
and the interpreter's stdlib. A determined attacker should be assumed
able to escape it. **Bind is 127.0.0.1 by default — do not expose this
server to a network you do not trust.** Full limits and known holes:
`docs/SPEC.md`.

## Divergences from the challenge (honest summary)

- The challenge specifies a browser WASM runtime (Pyodide/PyScript).
  This build executes code with the host CPython behind a local HTTP
  server instead (stdlib-only, no downloads, limits enforceable
  server-side). It only works while `playground.py` is running, and
  the Step 6 WASM failure cases are replaced by a server-unreachable
  message and localStorage-quota handling.
- No CodeMirror/Monaco: the editor is a textarea plus a self-contained
  regex highlighter preview, so the page works offline with no external
  assets. No auto-indent, bracket matching, or editor gutter.
- NOT built: autocomplete/code hints, multiple files, Pyodide library
  imports, server-side snippet storage/short links, stdin support.
  See `docs/SPEC.md` for the full step-by-step status table.

## Files

- `playground.py` — server + sandboxed child runner (single file,
  Python 3 standard library only).
- `docs/SPEC.md`, `docs/DESIGN.md`, `docs/TEST_PLAN.md` — spec,
  design, and test plan.
- `tests/test_playground.py` — unittest suite.

## Tests

```
python3 -m unittest discover -s tests -v
```

24 tests, all passing: routing/validation, execution, errors with line
numbers, timeout, recursion, output truncation, memory hog, sandbox
blocks (socket/subprocess/`os.system`/outside-file reads), temp-dir
isolation, and no cross-run contamination. Browser-only behaviour
(highlight colours, localStorage round-trips, dark-mode rendering) is
not headlessly testable; verify it manually with the checklist below.

## Manual browser checklist

1. Load the page, run `print("Hello, World!")` — output appears.
2. Run `print(1 / 0)` — "Line 1: ZeroDivisionError" + traceback.
3. Type `def` / a string / a comment — preview colours them.
4. Save a snippet, reload the page, load it back, delete it.
5. Run `while True: pass` — loading indicator shows, then a timeout
   message after ~5 s.
6. Toggle dark mode, reload — theme persists.
7. Copy share link, open it in a new tab — code loads into the editor.
