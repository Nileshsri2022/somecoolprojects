# SPEC — Build Your Own Strace

## Resolved challenge page

- Challenge: **Build Your Own Strace**
- Page (verified by reading it, 2026-10-25): https://codingchallenges.fyi/challenges/challenge-strace
- Original newsletter version (same steps, read as cross-check):
  https://codingchallenges.substack.com/p/coding-challenge-86-strace
- Tags (from the site's tag pages): intermediate, system programming.
- How the page was resolved: the challenge URL was not assumed. It was found
  via https://codingchallenges.fyi/challenges/tags → the intermediate tag page
  (https://codingchallenges.fyi/challenges/tags/intermediate/) → the
  "Build Your Own Strace" entry → the page above, which was read in full
  before any code was written.

## What the page asks for (steps, verbatim in substance)

- **Step 0** — Set up a Linux environment. Strace is a Linux tool that relies
  on Linux kernel functionality; on macOS/Windows a Linux VM is needed.
- **Step 1** — Run real `strace` against an existing command and study the
  output, e.g. abbreviated `strace ls`:
  `execve("/usr/bin/ls", ["ls"], 0xffffe735d390 /* 25 vars */) = 0`,
  `brk(NULL) = 0x...`, `faccessat(AT_FDCWD, "/etc/ld.so.preload", R_OK) = -1
  ENOENT (No such file or directory)`, `openat(AT_FDCWD, "/etc/ld.so.cache",
  O_RDONLY|O_CLOEXEC) = 3`, `fstat(3, {st_mode=S_IFREG|0644,
  st_size=28262, ...}) = 0`, `mmap(...) = 0x...`, `read(3, "\177ELF..."...,
  832) = 832`, `write(1, "..."..., 38) = 38`, `close(1) = 0`,
  `exit_group(0) = ?`, `+++ exited with 0 +++`.
- **Step 2** — Create a program that can launch another executable, using
  fork/exec (Python: the `subprocess` module is named on the page, but this
  implementation uses `os.fork`/`os.execvp` directly so the child can call
  `PTRACE_TRACEME` before exec — see DESIGN.md).
- **Step 3** — Attach `ptrace` to the launched executable, using
  `PTRACE_GETREGS` and `PTRACE_SYSCALL`, plus `wait` handling.
- **Step 4** — Translate register data into the syscall name and its
  arguments, using the Linux kernel syscall table.
- **Step 5** — Support the `-c` flag, printing a summary table like:
  ```
  % time     seconds  usecs/call     calls    errors syscall
  ------ ----------- ----------- --------- --------- ----------------
   25.39    0.002233          93        24           openat
   ...
  ------ ----------- ----------- --------- --------- ----------------
  100.00    0.008796                   147         4 total
  ```

## What this implementation does

```
python3 strace.py [-c] [--] command [args...]
python3 strace.py -h
```

- Traces only a child process it launches itself (its own child, never an
  already-running process, never a process owned by anyone else). There is
  no `-p` attach mode.
- Linux only, x86_64 only (the register layout and syscall numbers are the
  x86_64 ones). On any other platform it exits with a clear error.
- Trace lines go to stderr, exactly like real strace; the child's stdout and
  stderr pass through untouched, so `strace.py ls` still prints the `ls`
  output on stdout and the trace on stderr.
- Each completed syscall prints one line:
  `name(arg, arg, ...) = return`, e.g. `openat(AT_FDCWD, "/etc/hosts",
  O_RDONLY|O_CLOEXEC) = 3`, `write(1, "hi\n", 3) = 3`,
  `faccessat(AT_FDCWD, "/nonexistent", R_OK) = -1 ENOENT (No such file or directory)`.
- Errors print as `-1 ERRNO (strerror)`, matching the page's example.
- `exit_group` / `exit` print `= ?` and the tracer then prints
  `+++ exited with N +++` (or `+++ killed by SIG… +++` for signal death),
  matching the page.
- `-c` suppresses per-call lines and prints, at the end, the summary table
  in the page's format: `% time`, `seconds`, `usecs/call`, `calls`,
  `errors`, `syscall`, sorted by total time descending, with a `total` row.
  The child's own output still appears (on stdout) before the table, as in
  the page's `strace -c ls` example.
- The tracer propagates the child's exit status: it exits with the child's
  exit code, or 128 + signal number if the child died by a signal.

## Supported syscall subset (exact)

Decoding is implemented for the syscalls a typical dynamically-linked
command actually makes at startup, plus the common file/process/memory
calls. Argument formatting is specific (paths, flags, modes, buffers) for
these; every other known x86_64 number is printed by name with its raw
register arguments, and a completely unknown number prints as
`syscall_<nr>(...)`. The named table covers numbers 0–334 (plus
`pidfd_open` 434, `clone3` 435, `openat2` 437, `pidfd_getfd` 438); see
`SYSCALLS` in `strace.py` for the authoritative list.

Argument formatting that is syscall-specific:

| Syscall | Formatting |
|---|---|
| `read`, `pread64`, `readv` (entry buffer unknown) | buffer read back from the child at syscall exit, quoted, truncated with `...` after 32 bytes, like the page's `read(3, "\177ELF..."..., 832)` |
| `write`, `writev`, `sendto`, `sendmsg` | buffer read at syscall entry, same quoting/truncation |
| `open`, `openat`, `openat2`, `execve`, `execveat`, `access`, `faccessat`, `stat`, `lstat`, `newfstatat`, `statx`, `unlink`, `unlinkat`, `mkdir`, `mkdirat`, `rmdir`, `rename`, `renameat`, `renameat2`, `link`, `linkat`, `symlink`, `symlinkat`, `readlink`, `readlinkat`, `chmod`, `chown`, `mknod`, `truncate`, `chdir`, `statfs`, `fstatfs` | pathname read from the child as a C string; `-100` as the dirfd prints as `AT_FDCWD` |
| `execve`, `execveat` | argv printed as a `["a", "b"]` list; envp printed as `0x… /* N vars */` |
| `open`/`openat` flags | `O_RDONLY`, `O_WRONLY`, `O_RDWR`, `O_CREAT`, `O_EXCL`, `O_TRUNC`, `O_APPEND`, `O_NONBLOCK`, `O_CLOEXEC`, `O_DIRECTORY`, `O_NOFOLLOW`, `O_NOATIME`, `O_SYNC`, `O_DSYNC`, `O_DIRECT`, `O_LARGEFILE`, `O_NOCTTY`, `O_ASYNC`, combined with `\|`, access mode first |
| `faccessat` mode | `F_OK` / `R_OK` / `W_OK` / `X_OK` combinations |
| `mmap`, `mprotect` | `PROT_READ\|PROT_WRITE\|PROT_EXEC` / `PROT_NONE`; `MAP_SHARED\|MAP_PRIVATE\|MAP_ANONYMOUS\|MAP_FIXED\|MAP_DENYWRITE` etc. |
| `brk` | `NULL` for 0, otherwise a hex address |
| `fstat`, `newfstatat`, `stat`, `lstat` | `{st_mode=S_IFREG\|0644, st_size=N, ...}` decoded from the child's `struct stat` at exit (only `st_mode` and `st_size` are decoded; the rest is `...`, exactly as in the page's abbreviated form) |
| `mmap`, `brk`, `mremap`, `madvise` results, pointer arguments | hex `0x…` |
| `close`, `dup`, `dup2`, `dup3`, `fcntl`, `ioctl`, plain integer args | decimal integers |
| `exit`, `exit_group` | decimal code, result `?` |
| All other named syscalls | raw register values, decimal, in argument order |

String quoting: bytes are escaped like C (`\n`, `\t`, `\\`, `\"`, and
`\ooo` octal for other non-printables, e.g. `\177` for DEL), matching the
page's `"\177ELF"` example. Strings longer than 32 bytes print the first
32 bytes followed by `...` inside the quotes, then the closing quote is
omitted in the strace style (`"abc"...`); the count argument still shows
the full requested length.

## Deliberate divergences from the page

1. **Python instead of Go/C.** The page is language-agnostic (it names
   Python's `subprocess` module as an option). This build is Python 3
   standard library only, using `ctypes` for `ptrace` — no third-party
   dependency. Consequence: `ptrace` calls go through libc, which is
   slower than a C tracer, but the output format is the same.
2. **Fork/exec via `os.fork` + `PTRACE_TRACEME` + `os.execvp`, not
   `subprocess`.** `subprocess` cannot call `PTRACE_TRACEME` in the child
   between fork and exec without a `preexec_fn` that would itself be
   fragile; direct fork/exec is the standard tracer pattern and is what
   Step 3 requires. The observable behaviour (launch a command, trace it)
   is identical to Step 2.
3. **`-c` timing is wall time between syscall entry and exit stops.**
   Real strace measures kernel time more precisely; here the entry→exit
   stop interval includes tracer scheduling latency, so `usecs/call` is
   approximate, not a profiling-grade measurement. The table format and
   the counts/errors are exact.
4. **No `-f` (follow forks), no `-p` (attach), no `-o`, no `-e`, no `-s`
   string-size option, no signal-delivery lines.** None of these are in
   the page's steps; they are listed here as not built rather than
   silently omitted. Forked children are not followed (a `clone`/`fork`
   in the tracee returns normally, but the new process is untraced).
5. **Struct decoding is abbreviated.** Real strace decodes full structs
   (`stat`, `sigaction`, `pollfd`, …). Here only `struct stat`'s mode
   and size are decoded; other struct pointers print as hex addresses.
   This matches the page's own abbreviated `fstat` example (`...`).
6. **Buffer contents for `read` are read at exit, for `write` at entry.**
   This is the only way to show real data for both directions; a
   tracer that printed only at entry would show garbage for `read`.
   If the child memory cannot be read (e.g. the buffer was unmapped on
   exit), the buffer prints as its hex address instead of failing.

## NOT built (honest scope limits)

- Full strace compatibility: only the subset above is decoded; the rest
  is name + raw arguments. Do not use this as a drop-in replacement for
  system strace.
- Attaching to running processes (`-p`), following forks/threads (`-f`),
  filtering (`-e trace=…`), output files (`-o`), signal tracing
  (`--- SIG… ---` lines), multi-threaded tracees (only the main thread's
  syscalls are followed; a threaded child may interleave unpredictably).
- Non-x86_64 architectures, non-Linux systems, 32-bit tracees.
- Tracing processes you do not own, or any privileged operation: the
  tracer only ever traces its own child, runs unprivileged, and never
  escalates. It refuses to trace PID arguments because it takes no PID
  argument at all.
- Decoding of `ioctl` request codes, `fcntl` commands beyond the raw
  number, `socket` address structs, and `clone` flags beyond the raw
  number (these print as raw values).

## Usage

```
python3 strace.py [-c] [--] command [args...]
```

Examples:

```
python3 strace.py /bin/echo hello     # trace lines on stderr, "hello" on stdout
python3 strace.py -c /bin/true        # summary table on stderr only
python3 strace.py -- /bin/echo -n hi  # "--" separates flags from a command starting with "-"
```

Exit status: the child's exit status (or 128 + signal). Usage errors
(no command, unknown flag) exit with status 2 and a usage message on
stderr.
