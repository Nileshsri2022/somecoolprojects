# Build Your Own Strace

A small Linux x86_64 `strace`-like syscall tracer in Python 3 (standard
library only). It traces a child process it launches itself, via
`ptrace` (`PTRACE_TRACEME` / `PTRACE_SYSCALL` / `PTRACE_GETREGS`), and
prints one line per syscall on stderr — just like real strace.

Challenge page: https://codingchallenges.fyi/challenges/challenge-strace
(see `docs/SPEC.md` for the steps, the supported subset, divergences,
and everything that is deliberately not built).

## Usage

```
python3 strace.py [-c] [--] command [args...]
```

Examples:

```
python3 strace.py /bin/echo hello   # trace on stderr, "hello" on stdout
python3 strace.py -c /bin/true      # summary table only, on stderr
python3 strace.py -- /bin/echo -n hi
```

Sample output (from this machine, `/bin/echo hello`):

```
execve("/bin/echo", ["/bin/echo", "hello"], 0x... /* 55 vars */) = 0
brk(NULL) = 0x...
openat(AT_FDCWD, "/etc/ld.so.cache", O_RDONLY|O_CLOEXEC) = 3
fstat(3, {st_mode=S_IFREG|0644, st_size=41559, ...}) = 0
write(1, "hello\n", 6) = 6
exit_group(0) = ?
+++ exited with 0 +++
```

And `-c` prints the page's summary format:

```
% time     seconds  usecs/call     calls    errors syscall
------ ----------- ----------- --------- --------- ----------------
 60.09    0.000918         918         1         0 execve
 ...
------ ----------- ----------- --------- --------- ----------------
100.00    0.001528                    30         1 total
```

Exit status: the child's exit status (128 + signal number if the child
died by a signal). Usage errors exit 2.

## Files

- `strace.py` — the tracer (single file, stdlib only).
- `docs/SPEC.md` — challenge steps, supported syscall subset, divergences.
- `docs/DESIGN.md` — ptrace loop, register layout, memory reading.
- `docs/TEST_PLAN.md` — what is tested and what is not.
- `tests/test_strace.py` — unittest suite (pure logic + live tracing).

## Run the tests

```
python3 -m unittest discover -s tests -v
```

41 tests, all passing in this environment (live ptrace tests included —
they skip, rather than fake output, if ptrace is blocked in a sandbox).

## Scope limits (honest)

- Linux x86_64 only; traces only its own child (no `-p` attach, no `-f`
  follow-forks, no `-e`/`-o` filtering/output options — none of those
  are in the challenge steps).
- Only the syscall subset in `docs/SPEC.md` is decoded in detail;
  other known syscalls print by name with raw arguments, unknown
  numbers as `syscall_<nr>`. This is not a drop-in replacement for
  system strace.
- `-c` timings are entry→exit stop wall times (approximate, not
  profiling-grade); counts and errors are exact.
- Never traces processes you do not own and never runs privileged
  operations: it only ever traces its own child, read-only.
