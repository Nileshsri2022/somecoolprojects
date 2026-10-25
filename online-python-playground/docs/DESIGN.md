# DESIGN — Online Python Playground

## Architecture (one file, stdlib only)

```
browser ── GET / ──► playground.py (ThreadingHTTPServer)
browser ── POST /run (JSON {code}) ──► handler
        handler writes code to a fresh tempfile.TemporaryDirectory
        handler spawns: [sys.executable, playground.py, --child, codefile]
            preexec_fn: RLIMIT_CPU=6, RLIMIT_AS=256MiB,
                        RLIMIT_FSIZE=1MiB, RLIMIT_NPROC=64
            env: minimal (PATH, HOME/TMPDIR=tempdir, no network vars)
            stdin: DEVNULL, stdout/stderr: pipes
        parent: communicate(timeout=PLAYGROUND_TIMEOUT, default 5)
            on TimeoutExpired: kill, report timed_out
        child (--child): chdir(tempdir), install audit hook, run code
            with runpy.run_path, capture stdout/stderr via redirect,
            print a JSON result envelope to its own stdout
        parent parses the envelope; on any child failure it falls back
        to the raw captured output + a generic error.
        tempdir is deleted when the request ends.
```

Why one file with a `--child` mode instead of a separate runner module:
the server must spawn an interpreter running known code; re-invoking
itself keeps the project to a single deliverable file and avoids any
import-path confusion. The child mode never serves HTTP.

Why `runpy.run_path` with `__name__ == "__main__"`: user code behaves
as a script (so `if __name__ == "__main__"` blocks run), and tracebacks
point at the temp file, which the server rewrites to `<snippet>` and
extracts a line number from.

## Child audit hook

`sys.addaudithook` receives events before the operation runs; raising
an exception aborts it. Blocked:

- Events: `socket.connect`, `socket.bind`, `socket.listen`,
  `socket.connect_ex`, `subprocess.Popen`, `os.system`, `os.exec`,
  `os.fork`, `os.spawn`, `pty.spawn`, `ctypes.dlopen` / `ctypes.call`.
- Imports (`import` event, first arg is the module name): `socket`,
  `subprocess`, `multiprocessing`, `ctypes`, `urllib`, `http`,
  `ftplib`, `smtplib`, `requests`, `pty`, `socketserver`, `asyncio`
  is NOT blocked (it is legitimate, but its networking goes through
  the blocked `socket` module, so network use still fails).
- `open` events: resolved absolute path must be inside the run temp
  dir (any mode) or inside a stdlib directory (read-only modes only:
  `r`, `rb`, `rt`, etc.). Anything else raises `PermissionError`.
  Stdlib directories are computed from `sysconfig.get_paths()` plus
  `sys.base_prefix`/`sys.prefix` lib paths, so imports keep working
  while `/etc/passwd`, `~/.ssh`, and other users' files are refused.

This is best-effort (see SPEC.md "Known holes"). It stops the obvious
accidents and casual abuse — `import socket`, `open('/etc/passwd')`,
`os.system(...)`, `subprocess.run(...)` — which is what the tests check.

One subtlety found during testing: the server half of `playground.py`
imports `socket`/`subprocess`/`http`, so those modules are already in
`sys.modules` in the child and a cached import would bypass the audit
hook. The child therefore purges every blocked module from
`sys.modules` right after installing the hook, before running user
code (the child never serves HTTP, so it does not need them).

## Error reporting

- Syntax errors: `compile()` first in the child; on `SyntaxError` the
  envelope carries `type`, `message`, `lineno`, `traceback` (the
  formatted exception only — no fake frames).
- Runtime errors: the traceback from `runpy` is formatted with
  `traceback.format_exc()`. The server extracts the last frame whose
  filename is the snippet file and reports its line number; the page
  shows "Line N: <message>" plus the full traceback in a `<details>`
  block, and the editor line is not auto-jumped (no editor gutter).
- Timeout: parent kills the child; `timed_out: true`,
  `error.type: "TimeoutError"`, message states the limit in seconds.
- Memory: RLIMIT_AS makes over-allocation raise `MemoryError` inside
  the child, reported like any runtime error.

## Frontend (single inline page, no external assets)

- `<textarea id="editor">` for code (native undo/redo, copy/paste).
- A highlight preview `<pre>` below it, re-rendered on input by a
  small regex highlighter (keywords, builtins, strings, numbers,
  comments, decorators, function/class names). Escaping is done before
  highlighting so code cannot inject HTML.
- Run button + Ctrl+Enter; loading indicator (button disabled +
  "Running…" text) while a fetch is in flight; output `<pre>` and an
  error box with line number + failing source line when available.
- Snippets: `localStorage` key `pyplay.snippets` (JSON object
  name → code). Save (name prompt via a text input, not `prompt()`),
  list as buttons, Load, Delete. All storage access wrapped in
  try/catch → quota errors show a message instead of throwing.
- Share: "Copy share link" builds
  `#code=<base64url(utf8(code))>`; on load, a `#code=` fragment is
  decoded and placed in the editor. No server round-trip.
- Dark mode: toggle button, `body.dark` class, persisted as
  `pyplay.dark` in localStorage.
- Server-unreachable: a failed `fetch` shows "Could not reach the
  playground server — is `python3 playground.py` running?" instead of
  a blank panel. This is the Step 6 fallback for this architecture.
- Shortcuts guide: a short static list on the page (Run, Save, toggle
  theme, clear output).

## Limits / trade-offs

- ThreadingHTTPServer: concurrent runs are independent processes, so
  one run cannot corrupt another's state; the GIL is irrelevant.
- No persistence server-side: snippets live only in the browser.
- Binding: default `127.0.0.1`; `--host` is accepted but the README
  warns against binding a public interface (see SPEC.md sandbox note).
- Output cap 10,000 chars per stream, applied in the parent after the
  envelope is read, so a print-flood cannot grow memory unboundedly
  beyond the pipe buffer + cap handling (communicate() already bounds
  it to what the child produced within CPU/time limits).
