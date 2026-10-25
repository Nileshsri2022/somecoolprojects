#!/usr/bin/env python3
"""Tests for strace.py: pure formatting/stats logic always, plus live
ptrace tests that skip (not fake) when ptrace is blocked in the sandbox."""

import os
import struct
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import strace  # noqa: E402


class FakeMemory:
    """In-memory stand-in for ChildMemory, keyed by fake addresses."""

    def __init__(self):
        self.strings = {}   # addr -> bytes
        self.blobs = {}     # addr -> bytes
        self.argv_map = {}  # addr -> list[bytes]
        self.envp = {}      # addr -> int count
        self.stats = {}     # addr -> (mode, size)

    def c_string(self, addr, limit=4096):
        return self.strings.get(addr)

    def memory(self, addr, length):
        blob = self.blobs.get(addr)
        return None if blob is None else blob[:length]

    def argv(self, addr):
        return self.argv_map.get(addr)

    def envp_count(self, addr):
        return self.envp.get(addr)

    def stat(self, addr):
        return self.stats.get(addr)


def args6(*values):
    """Pad a syscall's register arguments to six slots."""
    values = list(values) + [0] * (6 - len(values))
    return tuple(values[:6])


class TestSyscallTable(unittest.TestCase):
    def test_known_numbers(self):
        self.assertEqual(strace.syscall_name(0), "read")
        self.assertEqual(strace.syscall_name(1), "write")
        self.assertEqual(strace.syscall_name(59), "execve")
        self.assertEqual(strace.syscall_name(257), "openat")
        self.assertEqual(strace.syscall_name(231), "exit_group")
        self.assertEqual(strace.syscall_name(302), "prlimit64")
        self.assertEqual(strace.syscall_name(9), "mmap")
        self.assertEqual(strace.syscall_name(217), "getdents64")
        self.assertEqual(strace.syscall_name(318), "getrandom")

    def test_unknown_number(self):
        self.assertEqual(strace.syscall_name(9999), "syscall_9999")


class TestFlags(unittest.TestCase):
    def test_open_flags(self):
        self.assertEqual(
            strace.format_flags(0o2000000, strace.OPEN_FLAGS, access_first=True),
            "O_RDONLY|O_CLOEXEC")
        self.assertEqual(
            strace.format_flags(0o101, strace.OPEN_FLAGS, access_first=True),
            "O_WRONLY|O_CREAT")
        self.assertEqual(
            strace.format_flags(0o1102, strace.OPEN_FLAGS, access_first=True),
            "O_RDWR|O_CREAT|O_TRUNC")

    def test_access_modes(self):
        self.assertEqual(strace.format_access(0), "F_OK")
        self.assertEqual(strace.format_access(4), "R_OK")
        self.assertEqual(strace.format_access(6), "R_OK|W_OK")
        self.assertEqual(strace.format_access(1), "X_OK")

    def test_prot_and_map(self):
        self.assertEqual(strace.format_prot(0), "PROT_NONE")
        self.assertEqual(strace.format_prot(3), "PROT_READ|PROT_WRITE")
        self.assertEqual(strace.format_flags(0x22, strace.MAP_FLAGS),
                         "MAP_PRIVATE|MAP_ANONYMOUS")

    def test_unknown_bits_as_hex(self):
        self.assertIn("0x", strace.format_flags(0x80000000, strace.MAP_FLAGS))

    def test_int32_fd(self):
        # fd -1 arrives as 0xFFFFFFFF, dirfd -100 as 0xFFFFFF9C.
        self.assertEqual(strace._format_arg("fd", 0xFFFFFFFF, (), None, {}), "-1")
        self.assertEqual(strace._format_arg("dirfd", 0xFFFFFF9C, (), None, {}),
                         "AT_FDCWD")
        self.assertEqual(strace._format_arg("dirfd", 3, (), None, {}), "3")


class TestStringFormatting(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(strace.format_c_bytes(b"hello"), '"hello"')

    def test_escapes(self):
        self.assertEqual(strace.format_c_bytes(b"a\nb\tc\\d\"e"),
                         '"a\\nb\\tc\\\\d\\"e"')

    def test_octal_for_nonprintable(self):
        # The page's ELF example: DEL is \177, 0x02 is \002.
        self.assertEqual(strace.format_c_bytes(b"\x7fELF\x02"),
                         '"\\177ELF\\002"')

    def test_truncation(self):
        data = b"x" * 40
        self.assertEqual(strace.format_c_bytes(data), '"' + "x" * 32 + '"...')
        self.assertEqual(strace.format_c_bytes(b"x" * 32), '"' + "x" * 32 + '"')


class TestReturnFormatting(unittest.TestCase):
    def test_success(self):
        self.assertEqual(strace.format_return("close", 0), "0")
        self.assertEqual(strace.format_return("openat", 3), "3")

    def test_errno(self):
        self.assertEqual(strace.format_return("faccessat", -2),
                         "-1 ENOENT (No such file or directory)")
        self.assertEqual(strace.format_return("openat", -13),
                         "-1 EACCES (Permission denied)")

    def test_pointer_returns_are_hex(self):
        self.assertEqual(strace.format_return("mmap", 0x7F000000), "0x7f000000")
        self.assertEqual(strace.format_return("brk", 0x55550000), "0x55550000")
        # A failed mmap is still an errno, not a hex pointer.
        self.assertEqual(strace.format_return("mmap", -12),
                         "-1 ENOMEM (Cannot allocate memory)")


class TestCallFormatting(unittest.TestCase):
    def test_openat(self):
        mem = FakeMemory()
        mem.strings[0x1000] = b"/etc/hosts"
        line = strace.format_call("openat", args6(0xFFFFFF9C, 0x1000, 0o2000000),
                                  3, mem)
        self.assertEqual(
            line, 'openat(AT_FDCWD, "/etc/hosts", O_RDONLY|O_CLOEXEC) = 3')

    def test_open_without_creat_omits_mode(self):
        mem = FakeMemory()
        mem.strings[0x1000] = b"/etc/hosts"
        line = strace.format_call("open", args6(0x1000, 0, 0o644), 3, mem)
        self.assertEqual(line, 'open("/etc/hosts", O_RDONLY) = 3')

    def test_open_with_creat_shows_mode(self):
        mem = FakeMemory()
        mem.strings[0x1000] = b"/tmp/x"
        line = strace.format_call("open", args6(0x1000, 0o101, 0o644), 3, mem)
        self.assertEqual(line, 'open("/tmp/x", O_WRONLY|O_CREAT, 0644) = 3')

    def test_faccessat_error(self):
        mem = FakeMemory()
        mem.strings[0x1000] = b"/nonexistent"
        line = strace.format_call("faccessat",
                                  args6(0xFFFFFF9C, 0x1000, 4, 0), -2, mem)
        self.assertEqual(
            line, 'faccessat(AT_FDCWD, "/nonexistent", R_OK) '
                  '= -1 ENOENT (No such file or directory)')

    def test_write_with_entry_buffer(self):
        line = strace.format_call("write", args6(1, 0x2000, 6), 6, None,
                                  {"buf": '"hello\\n"'})
        self.assertEqual(line, 'write(1, "hello\\n", 6) = 6')

    def test_read_buffer_from_memory(self):
        mem = FakeMemory()
        mem.blobs[0x2000] = b"\x7fELFhello"
        line = strace.format_call("read", args6(3, 0x2000, 832), 832, mem)
        self.assertEqual(line, 'read(3, "\\177ELFhello", 832) = 832')

    def test_execve(self):
        mem = FakeMemory()
        mem.strings[0x1000] = b"/bin/echo"
        mem.argv_map[0x2000] = [b"/bin/echo", b"hello"]
        mem.envp[0x3000] = 25
        line = strace.format_call("execve", args6(0x1000, 0x2000, 0x3000), 0, mem)
        self.assertEqual(
            line, 'execve("/bin/echo", ["/bin/echo", "hello"], '
                  '0x3000 /* 25 vars */) = 0')

    def test_fstat_struct(self):
        mem = FakeMemory()
        mem.stats[0x4000] = (0o100644, 28262)
        line = strace.format_call("fstat", args6(3, 0x4000), 0, mem)
        self.assertEqual(
            line, "fstat(3, {st_mode=S_IFREG|0644, st_size=28262, ...}) = 0")

    def test_fstat_unreadable_struct_is_hex(self):
        mem = FakeMemory()
        line = strace.format_call("fstat", args6(3, 0x4000), 0, mem)
        self.assertEqual(line, "fstat(3, 0x4000) = 0")

    def test_brk(self):
        self.assertEqual(strace.format_call("brk", args6(0), 0x55550000, None),
                         "brk(NULL) = 0x55550000")

    def test_mmap(self):
        line = strace.format_call(
            "mmap", args6(0, 8192, 3, 0x22, 0xFFFFFFFF, 0), 0x7F000000, None)
        self.assertEqual(
            line, "mmap(NULL, 8192, PROT_READ|PROT_WRITE, "
                  "MAP_PRIVATE|MAP_ANONYMOUS, -1, 0) = 0x7f000000")

    def test_exit_group(self):
        line = strace.format_call("exit_group", args6(0), None, None)
        self.assertEqual(line, "exit_group(0) = ?")

    def test_zero_arg_syscall(self):
        self.assertEqual(strace.format_call("getpid", args6(999, 888), 42, None),
                         "getpid() = 42")

    def test_unknown_syscall_raw(self):
        line = strace.format_call("syscall_9999", args6(1, 2, 0, 0, 0, 0), 0,
                                  None)
        self.assertEqual(line, "syscall_9999(1, 2) = 0")

    def test_entry_cached_path_survives_exec(self):
        # execve args captured at entry must win over exit-time memory.
        mem = FakeMemory()  # empty: exit-time read would fail
        cache = {("arg", 0): '"/bin/true"', ("arg", 1): '["/bin/true"]',
                 ("arg", 2): "0x3000 /* 55 vars */"}
        line = strace.format_call("execve", args6(0x1000, 0x2000, 0x3000), 0,
                                  mem, cache)
        self.assertEqual(
            line, 'execve("/bin/true", ["/bin/true"], '
                  '0x3000 /* 55 vars */) = 0')


class TestStatFormatting(unittest.TestCase):
    def test_types(self):
        self.assertEqual(strace.format_stat((0o100644, 10)),
                         "{st_mode=S_IFREG|0644, st_size=10, ...}")
        self.assertEqual(strace.format_stat((0o040755, 4096)),
                         "{st_mode=S_IFDIR|0755, st_size=4096, ...}")
        self.assertEqual(strace.format_stat((0o020620, 0)),
                         "{st_mode=S_IFCHR|0620, st_size=0, ...}")
        self.assertIsNone(strace.format_stat(None))


class TestStats(unittest.TestCase):
    def test_record_and_render(self):
        stats = strace.SyscallStats()
        stats.record("openat", 0.002, 3)
        stats.record("openat", 0.002, 3)
        stats.record("read", 0.001, -2)
        rendered = stats.render()
        lines = rendered.splitlines()
        self.assertEqual(lines[0],
                         "% time     seconds  usecs/call     calls    errors syscall")
        self.assertIn("openat", rendered)
        self.assertIn("read", rendered)
        self.assertTrue(lines[-1].endswith("total"))
        # openat first (more time), read has 1 error, total is 3 calls/1 error.
        self.assertLess(lines.index(next(l for l in lines if "openat" in l)),
                        lines.index(next(l for l in lines if "read" in l)))
        total = lines[-1].split()
        self.assertEqual(total[-3], "3")   # calls, then errors, then "total"
        self.assertEqual(total[-2], "1")   # errors
        # Percentages: openat 80.00, read 20.00.
        self.assertIn("80.00", rendered)
        self.assertIn("20.00", rendered)

    def test_empty_stats_no_division_by_zero(self):
        rendered = strace.SyscallStats().render()
        self.assertIn("total", rendered)
        self.assertIn("0.00", rendered)


class TestArgParsing(unittest.TestCase):
    def test_count_and_command(self):
        count, cmd = strace.parse_args(["-c", "/bin/true"])
        self.assertTrue(count)
        self.assertEqual(cmd, ["/bin/true"])

    def test_separator(self):
        count, cmd = strace.parse_args(["--", "/bin/echo", "-n"])
        self.assertFalse(count)
        self.assertEqual(cmd, ["/bin/echo", "-n"])

    def test_missing_command_exits_2(self):
        with self.assertRaises(SystemExit) as ctx:
            strace.parse_args([])
        self.assertEqual(ctx.exception.code, 2)

    def test_unknown_flag_exits_2(self):
        with self.assertRaises(SystemExit) as ctx:
            strace.parse_args(["-x", "/bin/true"])
        self.assertEqual(ctx.exception.code, 2)

    def test_command_args_preserved(self):
        count, cmd = strace.parse_args(["/bin/echo", "a b", "-n"])
        self.assertEqual(cmd, ["/bin/echo", "a b", "-n"])


def _ptrace_works():
    """Probe: run the tracer on /bin/true; True only if a real trace
    (not a ptrace-failed message) comes back."""
    here = os.path.join(os.path.dirname(__file__), "..", "strace.py")
    try:
        proc = subprocess.run(
            [sys.executable, here, "/bin/true"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    err = proc.stderr.decode("utf-8", "replace")
    return "ptrace failed" not in err and "execve(" in err


class TestLiveTracing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _ptrace_works():
            raise unittest.SkipTest(
                "ptrace blocked in this sandbox; live tracing unverified here")

    def _run(self, args):
        here = os.path.join(os.path.dirname(__file__), "..", "strace.py")
        return subprocess.run(
            [sys.executable, here] + args,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)

    def test_true(self):
        proc = self._run(["/bin/true"])
        self.assertEqual(proc.returncode, 0)
        err = proc.stderr.decode("utf-8", "replace")
        self.assertIn("execve(", err)
        self.assertIn("exit_group(", err)
        self.assertIn("+++ exited with 0 +++", err)

    def test_echo_passthrough_and_write(self):
        proc = self._run(["/bin/echo", "hello"])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode(), "hello\n")
        err = proc.stderr.decode("utf-8", "replace")
        self.assertIn('write(1, "hello\\n", 6) = 6', err)

    def test_false_exit_code(self):
        proc = self._run(["/bin/false"])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("+++ exited with 1 +++",
                      proc.stderr.decode("utf-8", "replace"))

    def test_count_mode(self):
        proc = self._run(["-c", "/bin/true"])
        self.assertEqual(proc.returncode, 0)
        err = proc.stderr.decode("utf-8", "replace")
        self.assertIn("% time", err)
        self.assertIn("total", err)
        self.assertNotIn("execve(", err)


if __name__ == "__main__":
    unittest.main()
