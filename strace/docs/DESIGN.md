# DESIGN — strace

## Overview

One file, `strace.py`, Python 3 standard library only (`os`, `sys`, `ctypes`,
`errno`, `signal`, `time`, `stat`). No third-party packages, no compiled
extension. The tracer is a classic ptrace syscall tracer for Linux x86_64.

## Architecture

```
main() -> parse_args() -> trace(command, count_only, out)
                              |
                    os.fork()
                     /      \
                  child     parent (tracer loop)
                    |            |
             PTRACE_TRACEME   waitpid loop, PTRACE_SYSCALL,
             SIGSTOP self     PTRACE_GETREGS at each stop,
             execvp(cmd)      format entry/exit, stats, print
```

### The child

1. `os.fork()`.
2. In the child: `libc.ptrace(PTRACE_TRACEME, 0, 0, 0)`, then
   `os.kill(os.getpid(), SIGSTOP)` so the parent can set options before
   the first syscall, then `os.execvp(command[0], command)`.
3. If `execvp` fails, the child writes the error to stderr and exits 127
   (the tracer reports it as a normal child exit; the `execve` failure
   itself is not faked as a traced line).

### The tracer loop

1. `waitpid` for the initial SIGSTOP, then `PTRACE_SETOPTIONS` with
   `PTRACE_O_TRACESYSGOOD` (0x1). With this option a syscall stop arrives
   as `SIGTRAP | 0x80`, which is how syscall stops are distinguished
   from genuine signals.
2. Repeatedly: `PTRACE_SYSCALL`, `waitpid`. On each stop:
   - Child exited → if a syscall entry is pending and it is `exit` /
     `exit_group`, emit `name(code) = ?`; then emit
     `+++ exited with N +++` (or `+++ killed by SIGNAME +++`) and stop.
   - Child stopped by a real signal → forward it with
     `PTRACE_SYSCALL` + that signal number, so the child is not silently
     stripped of signals (e.g. SIGINT from the terminal). Two
     exceptions: SIGSTOP (the initial stop) and SIGTRAP (the trap the
     kernel sends after a successful execve in a traced process) are
     tracer artefacts and are resumed with signal 0 — forwarding the
     exec SIGTRAP would kill the child with SIGTRAP.
   - Integer syscall arguments (fd, int, dirfd, signal) are read as
     signed 32-bit values from the low half of the register: the
     kernel leaves the high half of an int argument as zero, so fd -1
     arrives as 0xFFFFFFFF and dirfd -100 as 0xFFFFFF9C.
   - Syscall stop → `PTRACE_GETREGS` into a `user_regs_struct` (27
     `unsigned long long` fields in kernel order) and alternate
     entry/exit:
     - **Entry** (`in_syscall == False`): record syscall number
       (`orig_rax`), the six arguments (`rdi, rsi, rdx, r10, r8, r9`),
       and the monotonic start time. For `write`-family calls, read the
       buffer now (it is valid at entry) and cache the formatted text.
       For `execve`, read argv/envp now (argv pointers are valid at
       entry; envp is counted, not dumped).
     - **Exit** (`in_syscall == True`): read `rax` as the signed return
       value. For `read`-family calls, read the buffer now (it is
       filled at exit) and format it. For `stat`-family calls, read the
       child's `struct stat` now. Format the complete line, update the
       `-c` statistics (calls, errors, elapsed time), and print it
       unless `-c` is active.
3. `PTRACE_SYSCALL` is issued with no signal (0) on syscall stops, so
   the child is not injected with a spurious signal.

### Register / syscall table

- `user_regs_struct` field order follows the kernel's x86_64 struct:
  `r15, r14, r13, r12, rbp, rbx, r11, r10, r9, r8, rax, rcx, rdx, rsi,
  rdi, orig_rax, rip, cs, eflags, rsp, ss, fs_base, gs_base, ds, es,
  fs, gs`.
- `SYSCALLS` maps x86_64 number → name for 0–334 plus 434, 435, 437, 438.
  Unknown numbers format as `syscall_<nr>`.
- `ARG_SPECS` maps a syscall name → a tuple of argument kinds, one per
  register argument that is meaningful (trailing unused registers are
  dropped). Kinds: `fd`, `path`, `dirfd`, `buf` (buffer + a count taken
  from another argument), `count`, `int`, `addr`, `flags_open`,
  `flags_access`, `prot`, `mapflags`, `mode`, `argv`, `envp`, `statbuf`,
  `brkaddr`, `retptr` (hex pointer result), `signal`, `raw`.
- Argument formatting is a pure function of `(kind, value, regs,
  memory-reader)`, so it is unit-testable without ptrace (tests pass a
  fake memory reader).

### Reading child memory

`read_child_memory(pid, addr, length)` uses `PTRACE_PEEKDATA` word by
word through libc (`ctypes`, `c_long` return). A word read that fails
(errno set) stops the read and returns what was gathered so far.
`read_c_string(pid, addr, limit=4096)` stops at the first NUL byte.
`read_argv` reads a NULL-terminated array of pointers, then each string.
All readers are defensive: an unreadable address yields a hex address
(or an empty string for a buffer) rather than crashing the tracer.

### Formatting

- `format_c_string(data)`: C-style escaping (`\n \t \\ \"`, octal
  `\ooo` for other bytes < 0x20 or >= 0x7f, except that bytes are kept
  printable ASCII otherwise), wrapped in `"…"`, truncated to 32 bytes
  with `...` (strace style: `"first-32-bytes"...`).
- `format_flags(value, table, access_mode_first)`: splits the access
  mode bits first for open flags, then ORs the remaining named bits in
  table order; any leftover bits print as hex (`0x…`).
- `format_return(name, rax)`: `-4096 < rax < 0` → `-1 ERRNO (strerror)`
  via `errno.errorcode` / `os.strerror`; pointer-result syscalls
  (`mmap`, `brk`, `mremap`) → hex; everything else → signed decimal.
  `exit`/`exit_group` never reach this: they print `= ?`.
- `format_call(name, args, ret_text)` → `name(a, b) = ret`.
- `SyscallStats`: per-name `{calls, errors, total_seconds}`; `render_summary`
  produces the page's table (percent, seconds with 6 decimals,
  usecs/call as integer, calls, errors, name; `total` row; a zero-total
  table prints 0.00 everywhere rather than dividing by zero).

### `-c` summary

Statistics are accumulated on every syscall exit (entry time from
`time.monotonic()`). At child exit the table is rendered to stderr,
sorted by total seconds descending, ties broken by name. The `usecs/call`
column is `total_seconds * 1e6 / calls`, truncated to an integer, as in
real strace output.

### Safety / privilege

- Only the tracer's own child is traced (the child calls `PTRACE_TRACEME`
  on itself). No PID is ever accepted, no attach, no `PTRACE_ATTACH`.
- No setuid, no capability use, no writing to the tracee's memory
  (`PTRACE_POKEDATA` is never used), no register writes (`PTRACE_SETREGS`
  is never used). The tracer is read-only with respect to the tracee
  apart from letting it continue.
- Linux-only guard: `main()` refuses to run on non-Linux platforms and
  on non-x86_64 machines with a clear message, rather than producing
  wrong register interpretations.

## Failure modes

- `ptrace` blocked by the sandbox (e.g. seccomp denying `ptrace`):
  `PTRACE_TRACEME` / `PTRACE_SYSCALL` returns an error; the tracer
  prints `strace: ptrace failed: …` to stderr and exits 1, and does
  not fabricate trace lines. See TEST_PLAN.md for how this is handled
  in tests.
- Child command not found: child exits 127; tracer prints the
  `+++ exited with 127 +++` line (and, without `-c`, no syscall lines
  for the failed exec beyond the `execve` that failed — actually the
  failed execve is reported by the kernel as an exit stop, so the line
  is the exit line only).
- Child killed by a signal: `+++ killed by SIGTERM +++` style line,
  exit status 128 + signal number.
