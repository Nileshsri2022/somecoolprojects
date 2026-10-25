# SPEC — Online Python Playground

Source challenge: https://codingchallenges.fyi/challenges/challenge-online-python-playground
(read 2026-10-25; page live, not a 404.)

## What it is

A local web playground: an HTTP server serves one editor page. The user
writes Python in the browser, clicks Run (or Ctrl+Enter), and sees stdout,
stderr, and formatted errors (with line numbers) in an output panel below.

Run it:

```
python3 playground.py            # serves http://127.0.0.1:8000/
python3 playground.py --port 8765
PLAYGROUND_TIMEOUT=5 python3 playground.py   # seconds, default 5
```

## Challenge steps — status

| Step | Challenge asks | Status in this build |
|---|---|---|
| Step 0 | Dev environment, Python WASM runtime (Pyodide/PyScript) | DIVERGED (see below): no WASM runtime. Server-side CPython instead. |
| Step 1 | Editor + Run button, print stdout | DONE. Textarea editor, Run button, `/run` endpoint returns stdout. Tested: "Hello, World!", multiple lines, `print(2 + 2)`, variables. |
| Step 2 | Friendly errors with line numbers + traceback | DONE. Server parses the traceback, returns `{type, message, lineno, traceback}`; page shows the line number and the failing line, and the full traceback. Tested: missing colon (SyntaxError), undefined variable (NameError), division by zero (ZeroDivisionError). |
| Step 3 | Proper editor with syntax highlighting, undo/redo, shortcuts | PARTIAL (see divergences). Self-contained lightweight JS highlighter (no external editor library), native textarea undo/redo (Ctrl+Z/Ctrl+Y), Ctrl+Enter = Run, Ctrl+S = Save. |
| Step 4 | Save snippets to localStorage, list, load, delete | DONE, all client-side. Save with a name, list, load, delete; survives reload. Quota errors caught and shown. |
| Step 5 | Timeout for long-running code, loading indicator, memory warning | DONE (timeout + loading indicator + memory limit). Timeout default 5 s (env `PLAYGROUND_TIMEOUT`); infinite loop / deep recursion killed and reported as a timeout. Loading indicator shown while a run is in flight. Memory capped at 256 MiB (RLIMIT_AS) — a MemoryError is reported as an error, not a separate "warning" UI. |
| Step 6 | Graceful edge cases: WASM init failure, no WebAssembly, localStorage full | ADAPTED (see divergences). No WASM, so no WASM failure mode exists. Covered instead: server unreachable (clear "is the server running?" message), localStorage quota/full (caught, message shown), empty code (runs, empty output — no crash), `input()` with no stdin (EOFError shown, not a hang). |

## Going Further — status

- Dark mode: DONE (toggle, persisted in localStorage).
- Share snippets: DONE in a minimal form — "Copy share link" puts the code
  in the URL fragment (`#code=<base64url>`); opening such a link loads the
  code into the editor. No server-side storage, no short links.
- Keyboard shortcuts guide: DONE (a short list shown on the page).
- Autocomplete / code hints: NOT BUILT.
- Multiple files / projects: NOT BUILT (single snippet only).
- Import libraries (Pyodide packages): NOT BUILT. Only the Python standard
  library that ships with the host interpreter is importable, and the
  blocked-module list below removes the dangerous parts of it.
- No stdin support: NOT BUILT. Runs get empty stdin; `input()` raises
  `EOFError`, which is displayed like any other error.

## Deliberate divergences (honest, not silent)

1. **Server-side execution instead of browser WASM (Step 0/1/6).**
   The challenge specifies Pyodide/PyScript in the browser. This build
   executes code with the host CPython behind a local HTTP server
   instead, because: Python 3 standard library only was required, no
   external downloads, and the sandbox limits (timeout, rlimits, temp
   dir) are enforceable server-side. Consequence: the playground only
   works while `playground.py` is running, and code runs on the host
   machine, not in the browser sandbox. The page shows a clear message
   if the server cannot be reached.
2. **No CodeMirror/Monaco (Step 3).** External editor libraries (CDN)
   would break the stdlib-only, no-download property and fail offline.
   Instead the page has a lightweight, self-contained regex highlighter
   that colour-codes keywords, strings, numbers, comments, builtins and
   function definitions in a read-only preview pane below the editor,
   plus native textarea undo/redo and shortcuts. It is a highlighter,
   not a full editor: no auto-indent, bracket matching, or line numbers
   in the editing pane itself (error line numbers come from the run
   output, Step 2).
3. **Step 6 WASM cases do not apply.** Replaced by the server-unreachable
   and localStorage-quota cases above, which are the equivalent failure
   modes for this architecture.

## Execution limits (LOCAL DEMO SANDBOX ONLY — read this)

This is **not production-grade sandboxing and is not safe for untrusted
users**. It is a local demo for running your own code. A determined
attacker running code on this server can be expected to escape the
best-effort restrictions below; do not expose the server to a network
you do not trust (it binds 127.0.0.1 by default for exactly this reason).

Enforced per run (see DESIGN.md for details):

- Fresh temporary directory per run, used as the working directory;
  deleted afterwards. Relative file writes land there and are discarded.
- Wall-clock timeout: 5 s by default (`PLAYGROUND_TIMEOUT` env var).
- Resource limits via `preexec_fn` (Linux): CPU 6 s, address space
  256 MiB, file size 1 MiB, max 64 processes.
- Empty stdin; no network in the child environment (no proxy vars, and
  socket use is audit-blocked, see below).
- Child audit hook blocks: `socket.connect/bind/listen`, `subprocess`,
  `os.system/exec/fork`, `pty`, and imports of `socket`, `subprocess`,
  `multiprocessing`, `ctypes`, `urllib`, `http`, `ftplib`, `smtplib`,
  `requests`, `pty`, `os` sub-helpers are NOT blocked wholesale (too
  much legitimate code uses `os`), but `open()` outside the run temp
  dir and the interpreter's stdlib directories is blocked for both
  reading and writing.
- Minimal environment: only `PATH`, `HOME`/`TMPDIR` (pointing at the
  temp dir), `PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1`.
- Output capped at 10,000 characters (stdout and stderr separately);
  excess is truncated and flagged `truncated: true`.

Known holes (stated, not hidden): the audit hook runs in-process, so
exotic escape routes (e.g. via C extensions, `ctypes` alternatives
reached without importing `ctypes` by name, or interpreter bugs) are
not ruled out; resource limits are per-process best effort; and the
host interpreter version is whatever `python3` is on the machine.

## API

- `GET /` — the editor page (HTML, inline CSS/JS, no external assets).
- `POST /run` — JSON `{"code": "..."}` → JSON:
  `{"ok": bool, "stdout": str, "stderr": str, "error": null | {"type",
  "message", "lineno", "traceback"}, "timed_out": bool,
  "truncated": bool}`. HTTP 400 for missing/non-string `code` or bad JSON.
- Any other path → 404; any other method on `/run` → 405 (via handler).

## Files

- `playground.py` — the whole server + child runner (single file; when
  invoked with `--child <codefile>` it is the sandboxed runner).
- `tests/test_playground.py` — unittest suite (see TEST_PLAN.md).
