# TEST_PLAN — Online Python Playground

Suite: `tests/test_playground.py`, standard `unittest`, run with:

```
python3 -m unittest discover -s tests -v
```

The suite starts the real server as a subprocess on an ephemeral port
(`--port 0` is NOT used — http.server needs a concrete port, so the
suite picks a free port by binding port 0 in a throwaway socket, then
closes it before starting the server; the race is harmless for tests
because the suite retries the health check). `PLAYGROUND_TIMEOUT=2`
is set for the server subprocess so the timeout test finishes quickly;
the default of 5 s is covered by a unit test of the constant/default,
not by waiting 5 s. The server subprocess is terminated in `tearDownClass`
by explicit PID (`proc.terminate()` + `wait()`), never by pattern kill.

## Cases (all via real HTTP against the live server, plus unit checks)

Frontend / routing:

1. `GET /` → 200, HTML contains the editor textarea, Run button,
   output panel, localStorage snippet code, dark-mode toggle, and the
   share-link code.
2. Unknown path → 404; `GET /run` → 405; `POST /run` with bad JSON
   → 400; `POST /run` with missing/non-string `code` → 400.

Step 1 — execution:

3. `print("Hello, World!")` → ok, stdout exactly that line.
4. Multiple lines, `print(2 + 2)` → `4`, variables persist within a run.
5. Empty code → ok, empty stdout, no error.
6. `input()` → not ok, `EOFError` (empty stdin, no hang).

Step 2 — errors:

7. Missing colon → not ok, `SyntaxError`, lineno 1.
8. Undefined variable → `NameError` with a lineno.
9. Division by zero → `ZeroDivisionError` with a lineno.
10. Error envelope carries a traceback string mentioning the error type.

Step 5 — safeguards:

11. Infinite loop → `timed_out` true within ~2 s (+ tolerance),
    error type `TimeoutError`.
12. Deep recursion → not ok (RecursionError), does not hang the server;
    a subsequent run still works (server survives).
13. Huge output (`print("x" * 100000)`) → `truncated` true, stdout
    capped at 10,000 chars.
14. Memory hog (build a giant list) → not ok (MemoryError or killed
    child reported as an error), server still responsive afterwards.

Sandbox (best-effort, per SPEC.md):

15. `import socket` → blocked error (PermissionError-style message).
16. `import subprocess` / `os.system("echo hi")` → blocked error.
17. `open("/etc/passwd")` → blocked error.
18. Writing a relative file (`open("out.txt","w")`) inside the run
    succeeds within the run (it lands in the discarded temp dir) and
    does not create a file in the project directory — asserted by
    checking the project dir afterwards.
19. `print` after a blocked operation still runs in a fresh run
    (no cross-run contamination).

Going Further / misc:

20. Share-link format: page JS contains `#code=` handling (string
    check — browser behaviour itself is not headlessly testable here).
21. Default timeout constant is 5 s when `PLAYGROUND_TIMEOUT` is unset
    (unit check of the module default, no waiting).

## What is NOT tested headlessly (stated honestly)

- Visual syntax-highlight colours, undo/redo keystrokes, localStorage
  round-trips, and dark-mode rendering require a real browser; they
  are verified by inspecting the served HTML/JS (case 1, 20) and by
  the manual checklist in the README, not claimed as automated passes.
- The sandbox tests prove the documented blocks, not that the sandbox
  is escape-proof (see SPEC.md "Known holes").
