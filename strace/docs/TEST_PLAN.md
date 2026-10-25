# TEST_PLAN — strace

## How to run

```
cd ~/workspace/somecoolprojects/strace
python3 -m unittest discover -s tests -v
```

No third-party packages. Tests use only the standard library.

## What is tested (and how)

Tests are split into two layers, because ptrace may be restricted in
some sandboxes:

### Layer 1 — pure logic, always runs (no ptrace, no child process)

- **Syscall table**: known numbers map to the right names
  (`0 → read`, `1 → write`, `59 → execve`, `257 → openat`,
  `231 → exit_group`, `302 → prlimit64`, …); unknown numbers format
  as `syscall_<nr>`.
- **Flag decoding**: open flags (`O_RDONLY|O_CLOEXEC`,
  `O_WRONLY|O_CREAT|O_TRUNC`, access-mode precedence), access modes
  (`R_OK`, `F_OK`, combined `R_OK|W_OK`), `PROT_READ|PROT_WRITE`,
  `MAP_PRIVATE|MAP_ANONYMOUS`, unknown leftover bits as hex, `AT_FDCWD`
  for dirfd `-100`.
- **String formatting**: printable text unchanged, `\n`/`\t`/`\\`/`\"`
  escaping, non-printables as octal (`\177` for DEL — the page's ELF
  example), truncation to 32 bytes with `...`.
- **Return formatting**: `0 → 0`, `3 → 3`, `-2 → -1 ENOENT (No such file
  or directory)`, `-13 → -1 EACCES (Permission denied)`, pointer
  results (`mmap`/`brk`) as hex, negative pointer results as errno.
- **Call formatting**: full lines exactly as printed, e.g.
  `openat(AT_FDCWD, "/etc/hosts", O_RDONLY|O_CLOEXEC) = 3`,
  `faccessat(AT_FDCWD, "/x", R_OK) = -1 ENOENT (No such file or directory)`,
  `exit_group(0) = ?`, `brk(NULL) = 0x…`.
- **Argument formatting with a fake memory reader**: a fake
  `read_c_string`/`read_memory` is injected, so `openat` path decoding,
  `execve` argv-list and envp-count formatting, `fstat` struct decoding
  (`st_mode`/`st_size` from a fabricated `struct stat` byte string),
  and read/write buffer formatting are all verified without ptrace.
- **`-c` statistics**: `SyscallStats.record` counts calls and errors
  and accumulates time; `render_summary` produces the page's header,
  separator, per-syscall rows, and `total` row; percentages sum to
  100.00; empty stats render a zero table without division by zero;
  sorting is by total time descending.
- **Argument parsing**: `-c`, `--`, `-h`, unknown flags (exit 2),
  missing command (exit 2), command with arguments preserved verbatim.

### Layer 2 — live tracing, runs only if ptrace works here

These tests spawn the real tracer as a subprocess against `/bin/true`
and `/bin/echo`:

- Tracing `/bin/true` exits 0, prints `+++ exited with 0 +++` on
  stderr, and contains an `execve(` line and an `exit_group(` line.
- Tracing `/bin/echo hello` exits 0, prints `hello` on stdout
  (child output passes through), and contains a `write(1, "hello\n", 6)`
  line on stderr.
- `-c` mode for `/bin/true` prints no per-call lines but prints the
  summary header and a `total` row on stderr, and still exits 0.
- If ptrace is blocked in the sandbox, these tests **skip** (they check
  for the tracer's `ptrace failed` message and skip with a clear
  reason) instead of failing or faking output. The skip is reported in
  the test output and in the final report as "live tracing unverified
  here" — never as a pass.

## Manual checks (done by the builder, not in the suite)

- `python3 strace.py /bin/ls` in a scratch directory: trace lines on
  stderr, directory listing on stdout, exit 0.
- `python3 strace.py /bin/false`: exit 1, `+++ exited with 1 +++`.
- `python3 strace.py /nonexistent-command-xyz`: child exit 127.
- `python3 strace.py -c /bin/echo hi`: summary table only on stderr.
- Compare a handful of lines against system `strace` output for the
  same command (names and argument order, not byte-identical output —
  addresses and counts legitimately differ between runs).

## What is NOT tested

- Attaching to a running process, following forks, signal-delivery
  lines, ioctl/fcntl code decoding, full `struct stat` decoding beyond
  mode/size, non-x86_64 register layouts, threaded tracees — all out
  of scope per SPEC.md, so no test claims them.
- Exact byte-equality with system strace: addresses, file descriptors
  assigned by the kernel, and timing vary run to run; tests assert on
  structure and on specific lines that are deterministic.
