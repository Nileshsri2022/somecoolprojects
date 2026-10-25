#!/usr/bin/env python3
"""A small Linux x86_64 strace-like syscall tracer (Python stdlib only).

Traces only a child process it launches itself, via PTRACE_TRACEME /
PTRACE_SYSCALL / PTRACE_GETREGS. Trace lines go to stderr; the child's
stdout/stderr pass through untouched.

Usage: python3 strace.py [-c] [--] command [args...]
See README.md and docs/SPEC.md for the supported subset and limits.
"""

import ctypes
import errno
import os
import platform
import signal
import stat as statmod
import sys
import time

# ---------------------------------------------------------------------------
# ptrace constants (Linux x86_64)
# ---------------------------------------------------------------------------

PTRACE_TRACEME = 0
PTRACE_PEEKDATA = 2
PTRACE_SYSCALL = 24
PTRACE_GETREGS = 12
PTRACE_SETOPTIONS = 0x4200
PTRACE_O_TRACESYSGOOD = 0x1

PTR_RETURNS = {"mmap", "brk", "mremap", "shmat", "mmap2"}
WRITE_FAMILY = {"write", "writev", "sendto", "sendmsg", "pwrite64", "pwritev",
                "pwritev2"}
READ_FAMILY = {"read", "pread64", "readv", "recvfrom", "recvmsg", "recvmmsg"}

_libc_handle = None


def _libc():
    global _libc_handle
    if _libc_handle is None:
        _libc_handle = ctypes.CDLL("libc.so.6", use_errno=True)
        _libc_handle.ptrace.argtypes = [ctypes.c_ulong, ctypes.c_ulong,
                                 ctypes.c_void_p, ctypes.c_void_p]
        _libc_handle.ptrace.restype = ctypes.c_long
    return _libc_handle


class Regs(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "r15", "r14", "r13", "r12", "rbp", "rbx", "r11", "r10", "r9", "r8",
        "rax", "rcx", "rdx", "rsi", "rdi", "orig_rax", "rip", "cs",
        "eflags", "rsp", "ss", "fs_base", "gs_base", "ds", "es", "fs", "gs")]


def _ptrace(request, pid, addr, data):
    ctypes.set_errno(0)
    result = _libc().ptrace(request, pid, addr, data)
    err = ctypes.get_errno()
    return result, err


# ---------------------------------------------------------------------------
# Syscall table (x86_64)
# ---------------------------------------------------------------------------

_SYSCALL_NAMES = [
    (0, "read"), (1, "write"), (2, "open"), (3, "close"), (4, "stat"),
    (5, "fstat"), (6, "lstat"), (7, "poll"), (8, "lseek"), (9, "mmap"),
    (10, "mprotect"), (11, "munmap"), (12, "brk"), (13, "rt_sigaction"),
    (14, "rt_sigprocmask"), (15, "rt_sigreturn"), (16, "ioctl"),
    (17, "pread64"), (18, "pwrite64"), (19, "readv"), (20, "writev"),
    (21, "access"), (22, "pipe"), (23, "select"), (24, "sched_yield"),
    (25, "mremap"), (26, "msync"), (27, "mincore"), (28, "madvise"),
    (29, "shmget"), (30, "shmat"), (31, "shmctl"), (32, "dup"),
    (33, "dup2"), (34, "pause"), (35, "nanosleep"), (36, "getitimer"),
    (37, "alarm"), (38, "setitimer"), (39, "getpid"), (40, "sendfile"),
    (41, "socket"), (42, "connect"), (43, "accept"), (44, "sendto"),
    (45, "recvfrom"), (46, "sendmsg"), (47, "recvmsg"), (48, "shutdown"),
    (49, "bind"), (50, "listen"), (51, "getsockname"), (52, "getpeername"),
    (53, "socketpair"), (54, "setsockopt"), (55, "getsockopt"),
    (56, "clone"), (57, "fork"), (58, "vfork"), (59, "execve"),
    (60, "exit"), (61, "wait4"), (62, "kill"), (63, "uname"),
    (64, "semget"), (65, "semop"), (66, "semctl"), (67, "shmdt"),
    (68, "msgget"), (69, "msgsnd"), (70, "msgrcv"), (71, "msgctl"),
    (72, "fcntl"), (73, "flock"), (74, "fsync"), (75, "fdatasync"),
    (76, "truncate"), (77, "ftruncate"), (78, "getdents"), (79, "getcwd"),
    (80, "chdir"), (81, "fchdir"), (82, "rename"), (83, "mkdir"),
    (84, "rmdir"), (85, "creat"), (86, "link"), (87, "unlink"),
    (88, "symlink"), (89, "readlink"), (90, "chmod"), (91, "fchmod"),
    (92, "chown"), (93, "fchown"), (94, "lchown"), (95, "umask"),
    (96, "gettimeofday"), (97, "getrlimit"), (98, "getrusage"),
    (99, "sysinfo"), (100, "times"), (101, "ptrace"), (102, "getuid"),
    (103, "syslog"), (104, "getgid"), (105, "setuid"), (106, "setgid"),
    (107, "geteuid"), (108, "getegid"), (109, "setpgid"), (110, "getppid"),
    (111, "getpgrp"), (112, "setsid"), (113, "setreuid"), (114, "setregid"),
    (115, "getgroups"), (116, "setgroups"), (117, "setresuid"),
    (118, "getresuid"), (119, "setresgid"), (120, "getresgid"),
    (121, "getpgid"), (122, "setfsuid"), (123, "setfsgid"), (124, "getsid"),
    (125, "capget"), (126, "capset"), (127, "rt_sigpending"),
    (128, "rt_sigtimedwait"), (129, "rt_sigqueueinfo"),
    (130, "rt_sigsuspend"), (131, "sigaltstack"), (132, "utime"),
    (133, "mknod"), (134, "uselib"), (135, "personality"), (136, "ustat"),
    (137, "statfs"), (138, "fstatfs"), (139, "sysfs"),
    (140, "getpriority"), (141, "setpriority"), (142, "sched_setparam"),
    (143, "sched_getparam"), (144, "sched_setscheduler"),
    (145, "sched_getscheduler"), (146, "sched_get_priority_max"),
    (147, "sched_get_priority_min"), (148, "sched_rr_get_interval"),
    (149, "mlock"), (150, "munlock"), (151, "mlockall"),
    (152, "munlockall"), (153, "vhangup"), (154, "modify_ldt"),
    (155, "pivot_root"), (156, "_sysctl"), (157, "prctl"),
    (158, "arch_prctl"), (159, "adjtimex"), (160, "setrlimit"),
    (161, "chroot"), (162, "sync"), (163, "acct"), (164, "settimeofday"),
    (165, "mount"), (166, "umount2"), (167, "swapon"), (168, "swapoff"),
    (169, "reboot"), (170, "sethostname"), (171, "setdomainname"),
    (172, "iopl"), (173, "ioperm"), (174, "create_module"),
    (175, "init_module"), (176, "delete_module"),
    (177, "get_kernel_syms"), (178, "query_module"), (179, "quotactl"),
    (180, "nfsservctl"), (181, "getpmsg"), (182, "putpmsg"),
    (183, "afs_syscall"), (184, "tuxcall"), (185, "security"),
    (186, "gettid"), (187, "readahead"), (188, "setxattr"),
    (189, "lsetxattr"), (190, "fsetxattr"), (191, "getxattr"),
    (192, "lgetxattr"), (193, "fgetxattr"), (194, "listxattr"),
    (195, "llistxattr"), (196, "flistxattr"), (197, "removexattr"),
    (198, "lremovexattr"), (199, "fremovexattr"), (200, "tkill"),
    (201, "time"), (202, "futex"), (203, "sched_setaffinity"),
    (204, "sched_getaffinity"), (205, "set_thread_area"),
    (206, "io_setup"), (207, "io_destroy"), (208, "io_getevents"),
    (209, "io_submit"), (210, "io_cancel"), (211, "get_thread_area"),
    (212, "lookup_dcookie"), (213, "epoll_create"), (214, "epoll_ctl_old"),
    (215, "epoll_wait_old"), (216, "remap_file_pages"),
    (217, "getdents64"), (218, "set_tid_address"),
    (219, "restart_syscall"), (220, "semtimedop"), (221, "fadvise64"),
    (222, "timer_create"), (223, "timer_settime"), (224, "timer_gettime"),
    (225, "timer_getover"), (226, "timer_delete"), (227, "clock_settime"),
    (228, "clock_gettime"), (229, "clock_getres"),
    (230, "clock_nanosleep"), (231, "exit_group"), (232, "epoll_wait"),
    (233, "epoll_ctl"), (234, "tgkill"), (235, "utimes"),
    (236, "vserver"), (237, "mbind"), (238, "set_mempolicy"),
    (239, "get_mempolicy"), (240, "mq_open"), (241, "mq_unlink"),
    (242, "mq_timedsend"), (243, "mq_timedreceive"), (244, "mq_notify"),
    (245, "mq_getsetattr"), (246, "kexec_load"), (247, "waitid"),
    (248, "add_key"), (249, "request_key"), (250, "keyctl"),
    (251, "ioprio_set"), (252, "ioprio_get"), (253, "inotify_init"),
    (254, "inotify_add_watch"), (255, "inotify_rm_watch"),
    (256, "migrate_pages"), (257, "openat"), (258, "mkdirat"),
    (259, "mknodat"), (260, "fchownat"), (261, "futimesat"),
    (262, "newfstatat"), (263, "unlinkat"), (264, "renameat"),
    (265, "linkat"), (266, "symlinkat"), (267, "readlinkat"),
    (268, "fchmodat"), (269, "faccessat"), (270, "pselect6"),
    (271, "ppoll"), (272, "unshare"), (273, "set_robust_list"),
    (274, "get_robust_list"), (275, "splice"), (276, "tee"),
    (277, "sync_file_range"), (278, "vmsplice"), (279, "move_pages"),
    (280, "utimensat"), (281, "epoll_pwait"), (282, "signalfd"),
    (283, "timerfd_create"), (284, "eventfd"), (285, "fallocate"),
    (286, "timerfd_settime"), (287, "timerfd_gettime"), (288, "accept4"),
    (289, "signalfd4"), (290, "eventfd2"), (291, "epoll_create1"),
    (292, "dup3"), (293, "pipe2"), (294, "inotify_init1"),
    (295, "preadv"), (296, "pwritev"), (297, "rt_tgsigqueueinfo"),
    (298, "perf_event_open"), (299, "recvmmsg"), (300, "fanotify_init"),
    (301, "fanotify_mark"), (302, "prlimit64"), (303, "name_to_handle_at"),
    (304, "open_by_handle_at"), (305, "clock_adjtime"), (306, "syncfs"),
    (307, "sendmmsg"), (308, "setns"), (309, "getcpu"),
    (310, "process_vm_readv"), (311, "process_vm_writev"), (312, "kcmp"),
    (313, "finit_module"), (314, "sched_setattr"), (315, "sched_getattr"),
    (316, "renameat2"), (317, "seccomp"), (318, "getrandom"),
    (319, "memfd_create"), (320, "kexec_file_load"), (321, "bpf"),
    (322, "execveat"), (323, "userfaultfd"), (324, "membarrier"),
    (325, "mlock2"), (326, "copy_file_range"), (327, "preadv2"),
    (328, "pwritev2"), (329, "pkey_mprotect"), (330, "pkey_alloc"),
    (331, "pkey_free"), (332, "statx"), (333, "io_pgetevents"),
    (334, "rseq"), (434, "pidfd_open"), (435, "clone3"),
    (437, "openat2"), (438, "pidfd_getfd"),
]
SYSCALLS = dict(_SYSCALL_NAMES)


def syscall_name(nr):
    """Name for a syscall number, or syscall_<nr> if unknown."""
    return SYSCALLS.get(nr, "syscall_%d" % nr)


# ---------------------------------------------------------------------------
# Formatting (pure functions; testable without ptrace)
# ---------------------------------------------------------------------------

def to_signed(value):
    value &= (1 << 64) - 1
    if value >= (1 << 63):
        value -= 1 << 64
    return value


def format_c_bytes(data):
    """Quote bytes C-style, truncating to 32 bytes with '...'."""
    if data is None:
        return None
    shown = data[:32]
    out = []
    for byte in shown:
        if byte == 0x0A:
            out.append("\\n")
        elif byte == 0x09:
            out.append("\\t")
        elif byte == 0x0D:
            out.append("\\r")
        elif byte == 0x5C:
            out.append("\\\\")
        elif byte == 0x22:
            out.append('\\"')
        elif 0x20 <= byte < 0x7F:
            out.append(chr(byte))
        else:
            out.append("\\%03o" % byte)
    text = "".join(out)
    if len(data) > 32:
        return '"%s"...' % text
    return '"%s"' % text


def format_flags(value, table, access_first=False):
    """Decode a flag word. table: list of (bit, name) in display order."""
    parts = []
    rest = value
    if access_first:
        mode = value & 3
        parts.append({0: "O_RDONLY", 1: "O_WRONLY", 2: "O_RDWR"}[mode])
        rest &= ~3
    for bit, name in table:
        if rest & bit:
            parts.append(name)
            rest &= ~bit
    if rest:
        parts.append("0x%x" % rest)
    return "|".join(parts) if parts else "0"


OPEN_FLAGS = [
    (0o100, "O_CREAT"), (0o200, "O_EXCL"), (0o400, "O_NOCTTY"),
    (0o1000, "O_TRUNC"), (0o2000, "O_APPEND"), (0o4000, "O_NONBLOCK"),
    (0o10000, "O_DSYNC"), (0o20000, "O_ASYNC"), (0o40000, "O_DIRECT"),
    (0o100000, "O_LARGEFILE"), (0o200000, "O_DIRECTORY"),
    (0o400000, "O_NOFOLLOW"), (0o1000000, "O_NOATIME"),
    (0o2000000, "O_CLOEXEC"), (0o4010000, "O_SYNC"),
]
PROT_FLAGS = [(1, "PROT_READ"), (2, "PROT_WRITE"), (4, "PROT_EXEC")]
MAP_FLAGS = [
    (0x01, "MAP_SHARED"), (0x02, "MAP_PRIVATE"), (0x10, "MAP_FIXED"),
    (0x20, "MAP_ANONYMOUS"), (0x800, "MAP_DENYWRITE"),
    (0x1000, "MAP_EXECUTABLE"), (0x2000, "MAP_LOCKED"),
    (0x4000, "MAP_NORESERVE"), (0x8000, "MAP_POPULATE"),
    (0x10000, "MAP_NONBLOCK"), (0x20000, "MAP_STACK"),
    (0x40000, "MAP_HUGETLB"),
]
ACCESS_FLAGS = [(4, "R_OK"), (2, "W_OK"), (1, "X_OK")]
AT_FLAGS = [(0x100, "AT_SYMLINK_NOFOLLOW"), (0x200, "AT_EACCESS"),
            (0x1000, "AT_EMPTY_PATH"), (0x800, "AT_NO_AUTOMOUNT")]

_SIGNAL_NAMES = {getattr(signal, name): name for name in dir(signal)
                 if name.startswith("SIG") and "_" not in name[3:]}


def format_access(value):
    if value == 0:
        return "F_OK"
    parts = [name for bit, name in ACCESS_FLAGS if value & bit]
    rest = value & ~7
    if rest:
        parts.append("0x%x" % rest)
    return "|".join(parts) if parts else "0"


def format_prot(value):
    if value == 0:
        return "PROT_NONE"
    return format_flags(value, PROT_FLAGS)


def format_return(name, rax):
    """Format a syscall return value (signed rax)."""
    if -4096 < rax < 0:
        err_no = -rax
        err_name = errno.errorcode.get(err_no, "ERR%d" % err_no)
        try:
            err_text = os.strerror(err_no)
        except (ValueError, OSError):
            err_text = "Unknown error"
        return "-1 %s (%s)" % (err_name, err_text)
    if name in PTR_RETURNS:
        return "0x%x" % (rax & ((1 << 64) - 1))
    return str(rax)


def format_stat(stat_tuple):
    """Format a decoded struct stat as {st_mode=..., st_size=..., ...}."""
    if stat_tuple is None:
        return None
    mode, size = stat_tuple
    fmt = statmod.S_IFMT(mode)
    type_name = {
        statmod.S_IFREG: "S_IFREG", statmod.S_IFDIR: "S_IFDIR",
        statmod.S_IFCHR: "S_IFCHR", statmod.S_IFBLK: "S_IFBLK",
        statmod.S_IFIFO: "S_IFIFO", statmod.S_IFLNK: "S_IFLNK",
        statmod.S_IFSOCK: "S_IFSOCK",
    }.get(fmt)
    if type_name is not None:
        mode_text = "%s|%04o" % (type_name, mode & 0o7777)
    else:
        mode_text = "%04o" % (mode & 0o7777)
    return "{st_mode=%s, st_size=%d, ...}" % (mode_text, size)


# Argument specs: descriptor per register argument.
# Kinds: fd, dirfd, path, int, count, addr, brkaddr, mode, sig,
#   flags_open, flags_access, prot, mapflags, statbuf, argv, envp,
#   ("buf", count_index)
ARG_SPECS = {
    "read": ("fd", ("buf", 2), "count"),
    "write": ("fd", ("buf", 2), "count"),
    "pread64": ("fd", ("buf", 2), "count", "int"),
    "pwrite64": ("fd", ("buf", 2), "count", "int"),
    "readv": ("fd", "addr", "count"),
    "writev": ("fd", "addr", "count"),
    "preadv": ("fd", "addr", "count", "int"),
    "pwritev": ("fd", "addr", "count", "int"),
    "preadv2": ("fd", "addr", "count", "int", "int"),
    "pwritev2": ("fd", "addr", "count", "int", "int"),
    "open": ("path", "flags_open", "mode"),
    "openat": ("dirfd", "path", "flags_open", "mode"),
    "openat2": ("dirfd", "path", "addr", "count"),
    "creat": ("path", "mode"),
    "close": ("fd",),
    "stat": ("path", "statbuf"),
    "lstat": ("path", "statbuf"),
    "fstat": ("fd", "statbuf"),
    "newfstatat": ("dirfd", "path", "statbuf", "int"),
    "statx": ("dirfd", "path", "int", "int", "addr"),
    "access": ("path", "flags_access"),
    "faccessat": ("dirfd", "path", "flags_access", "atflags"),
    "faccessat2": ("dirfd", "path", "flags_access", "atflags"),
    "execve": ("path", "argv", "envp"),
    "execveat": ("dirfd", "path", "argv", "envp", "int"),
    "mmap": ("addr", "count", "prot", "mapflags", "fd", "int"),
    "mprotect": ("addr", "count", "prot"),
    "munmap": ("addr", "count"),
    "mremap": ("addr", "count", "count", "mapflags", "addr"),
    "brk": ("brkaddr",),
    "madvise": ("addr", "count", "int"),
    "ioctl": ("fd", "int", "addr"),
    "fcntl": ("fd", "int", "int"),
    "dup": ("fd",),
    "dup2": ("fd", "fd"),
    "dup3": ("fd", "fd", "int"),
    "pipe": ("addr",),
    "pipe2": ("addr", "int"),
    "lseek": ("fd", "int", "int"),
    "getcwd": ("addr", "count"),
    "chdir": ("path",),
    "fchdir": ("fd",),
    "mkdir": ("path", "mode"),
    "mkdirat": ("dirfd", "path", "mode"),
    "rmdir": ("path",),
    "unlink": ("path",),
    "unlinkat": ("dirfd", "path", "int"),
    "rename": ("path", "path"),
    "renameat": ("dirfd", "path", "dirfd", "path"),
    "renameat2": ("dirfd", "path", "dirfd", "path", "int"),
    "link": ("path", "path"),
    "linkat": ("dirfd", "path", "dirfd", "path", "int"),
    "symlink": ("path", "path"),
    "symlinkat": ("path", "dirfd", "path"),
    "readlink": ("path", "addr", "count"),
    "readlinkat": ("dirfd", "path", "addr", "count"),
    "chmod": ("path", "mode"),
    "fchmod": ("fd", "mode"),
    "fchmodat": ("dirfd", "path", "mode", "int"),
    "chown": ("path", "int", "int"),
    "fchown": ("fd", "int", "int"),
    "lchown": ("path", "int", "int"),
    "fchownat": ("dirfd", "path", "int", "int", "int"),
    "truncate": ("path", "int"),
    "ftruncate": ("fd", "int"),
    "umask": ("mode",),
    "mknod": ("path", "mode", "int"),
    "mknodat": ("dirfd", "path", "mode", "int"),
    "statfs": ("path", "addr"),
    "fstatfs": ("fd", "addr"),
    "sendto": ("fd", ("buf", 2), "count", "int", "addr", "int"),
    "recvfrom": ("fd", ("buf", 2), "count", "int", "addr", "addr"),
    "sendmsg": ("fd", "addr", "int"),
    "recvmsg": ("fd", "addr", "int"),
    "socket": ("int", "int", "int"),
    "connect": ("fd", "addr", "int"),
    "bind": ("fd", "addr", "int"),
    "listen": ("fd", "int"),
    "accept": ("fd", "addr", "addr"),
    "accept4": ("fd", "addr", "addr", "int"),
    "getsockname": ("fd", "addr", "addr"),
    "getpeername": ("fd", "addr", "addr"),
    "socketpair": ("int", "int", "int", "addr"),
    "setsockopt": ("fd", "int", "int", "addr", "int"),
    "getsockopt": ("fd", "int", "int", "addr", "addr"),
    "shutdown": ("fd", "int"),
    "sendfile": ("fd", "fd", "addr", "count"),
    "exit": ("int",),
    "exit_group": ("int",),
    "kill": ("int", "sig"),
    "tkill": ("int", "sig"),
    "tgkill": ("int", "int", "sig"),
    "wait4": ("int", "addr", "int", "addr"),
    "waitid": ("int", "int", "addr", "int"),
    "clone": ("int", "addr", "addr", "addr", "addr"),
    "fork": (),
    "vfork": (),
    "getpid": (),
    "getuid": (),
    "getgid": (),
    "geteuid": (),
    "getegid": (),
    "getppid": (),
    "getpgrp": (),
    "gettid": (),
    "sched_yield": (),
    "pause": (),
    "sync": (),
    "getrandom": ("addr", "count", "int"),
    "memfd_create": ("path", "int"),
    "set_tid_address": ("addr",),
    "set_robust_list": ("addr", "count"),
    "get_robust_list": ("int", "addr", "addr"),
    "nanosleep": ("addr", "addr"),
    "clock_gettime": ("int", "addr"),
    "clock_getres": ("int", "addr"),
    "clock_nanosleep": ("int", "int", "addr", "addr"),
    "gettimeofday": ("addr", "addr"),
    "uname": ("addr",),
    "sysinfo": ("addr",),
    "times": ("addr",),
    "getrlimit": ("int", "addr"),
    "setrlimit": ("int", "addr"),
    "prlimit64": ("int", "int", "addr", "addr"),
    "getrusage": ("int", "addr"),
    "futex": ("addr", "int", "int", "addr", "addr", "int"),
    "rt_sigaction": ("sig", "addr", "addr", "count"),
    "rt_sigprocmask": ("int", "addr", "addr", "count"),
    "rt_sigreturn": (),
    "poll": ("addr", "int", "int"),
    "ppoll": ("addr", "int", "addr", "addr"),
    "select": ("int", "addr", "addr", "addr", "addr"),
    "pselect6": ("int", "addr", "addr", "addr", "addr", "addr"),
    "epoll_create": ("int",),
    "epoll_create1": ("int",),
    "epoll_ctl": ("int", "int", "int", "addr"),
    "epoll_wait": ("int", "addr", "int", "int"),
    "epoll_pwait": ("int", "addr", "int", "int", "addr", "count"),
    "inotify_init": (),
    "inotify_init1": ("int",),
    "inotify_add_watch": ("fd", "path", "int"),
    "inotify_rm_watch": ("fd", "int"),
    "eventfd": ("int",),
    "eventfd2": ("int", "int"),
    "signalfd": ("fd", "addr", "count"),
    "signalfd4": ("fd", "addr", "count", "int"),
    "timerfd_create": ("int", "int"),
    "timerfd_settime": ("fd", "int", "addr", "addr"),
    "timerfd_gettime": ("fd", "addr"),
    "fallocate": ("fd", "int", "int", "int"),
    "splice": ("fd", "addr", "fd", "addr", "count", "int"),
    "tee": ("fd", "fd", "count", "int"),
    "vmsplice": ("fd", "addr", "count", "int"),
    "copy_file_range": ("fd", "addr", "fd", "addr", "count", "int"),
    "fsync": ("fd",),
    "fdatasync": ("fd",),
    "flock": ("fd", "int"),
    "msync": ("addr", "count", "int"),
    "mincore": ("addr", "count", "addr"),
    "mlock": ("addr", "count"),
    "munlock": ("addr", "count"),
    "mlockall": ("int",),
    "munlockall": (),
    "readahead": ("fd", "int", "count"),
    "fadvise64": ("fd", "int", "count", "int"),
    "sync_file_range": ("fd", "int", "int", "int"),
    "syncfs": ("fd",),
    "utimensat": ("dirfd", "path", "addr", "int"),
    "futimesat": ("dirfd", "path", "addr"),
    "utimes": ("path", "addr"),
    "alarm": ("int",),
    "getitimer": ("int", "addr"),
    "setitimer": ("int", "addr", "addr"),
    "getpriority": ("int", "int"),
    "setpriority": ("int", "int", "int"),
    "sched_setparam": ("int", "addr"),
    "sched_getparam": ("int", "addr"),
    "sched_setscheduler": ("int", "int", "addr"),
    "sched_getscheduler": ("int",),
    "sched_get_priority_max": ("int",),
    "sched_get_priority_min": ("int",),
    "sched_rr_get_interval": ("int", "addr"),
    "sched_setaffinity": ("int", "count", "addr"),
    "sched_getaffinity": ("int", "count", "addr"),
    "sched_setattr": ("int", "addr", "int"),
    "sched_getattr": ("int", "addr", "count", "int"),
    "setns": ("fd", "int"),
    "getcpu": ("addr", "addr", "addr"),
    "kcmp": ("int", "int", "int", "int", "int"),
    "seccomp": ("int", "int", "addr"),
    "bpf": ("int", "addr", "int"),
    "userfaultfd": ("int",),
    "membarrier": ("int", "int"),
    "mlock2": ("addr", "count", "int"),
    "pkey_mprotect": ("addr", "count", "prot", "int"),
    "pkey_alloc": ("int", "int"),
    "pkey_free": ("int",),
    "io_setup": ("int", "addr"),
    "io_destroy": ("addr",),
    "io_submit": ("addr", "int", "addr"),
    "io_cancel": ("addr", "addr", "addr"),
    "io_getevents": ("addr", "int", "int", "addr", "addr"),
    "mq_open": ("path", "int", "mode", "addr"),
    "mq_unlink": ("path",),
    "mq_timedsend": ("int", "addr", "count", "int", "addr"),
    "mq_timedreceive": ("int", "addr", "count", "addr", "addr"),
    "mq_notify": ("int", "addr"),
    "mq_getsetattr": ("int", "addr", "addr"),
}


def _to_int32(value):
    """C int arguments arrive in 64-bit registers with only the low
    32 bits meaningful (e.g. fd -1 appears as 0xFFFFFFFF, -100 as
    0xFFFFFF9C), so interpret fd/int/dirfd/signal as signed 32-bit."""
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value >= (1 << 31) else value


def _format_arg(kind, value, args, mem, entry_cache):
    signed = _to_int32(value)
    if kind == "fd" or kind == "int":
        return str(signed)
    if kind == "count":
        return str(value)
    if kind == "dirfd":
        return "AT_FDCWD" if signed == -100 else str(signed)
    if kind == "addr":
        return "NULL" if value == 0 else "0x%x" % value
    if kind == "brkaddr":
        return "NULL" if value == 0 else "0x%x" % value
    if kind == "mode":
        return "%04o" % (value & 0o7777)
    if kind == "sig":
        return _SIGNAL_NAMES.get(signed, str(signed))
    if kind == "flags_open":
        return format_flags(value, OPEN_FLAGS, access_first=True)
    if kind == "flags_access":
        return format_access(value)
    if kind == "atflags":
        return format_flags(value, AT_FLAGS)
    if kind == "prot":
        return format_prot(value)
    if kind == "mapflags":
        return format_flags(value, MAP_FLAGS)
    if kind == "path":
        if mem is None:
            return "0x%x" % value
        data = mem.c_string(value)
        return format_c_bytes(data) if data is not None else "0x%x" % value
    if kind == "statbuf":
        if mem is None:
            return "0x%x" % value
        text = format_stat(mem.stat(value))
        return text if text is not None else "0x%x" % value
    if kind == "argv":
        if mem is None:
            return "0x%x" % value
        items = mem.argv(value)
        if items is None:
            return "0x%x" % value
        return "[%s]" % ", ".join(format_c_bytes(item) for item in items)
    if kind == "envp":
        if mem is None:
            return "0x%x" % value
        count = mem.envp_count(value)
        if count is None:
            return "0x%x" % value
        return "0x%x /* %d vars */" % (value, count)
    return str(signed)


def format_call(name, args, ret, mem=None, entry_cache=None):
    """Format one completed syscall. args: 6 raw register values.

    ret: signed return value, or None for exit/exit_group ('?').
    entry_cache: dict with a pre-read 'buf' text for write-family calls.
    """
    entry_cache = entry_cache or {}
    spec = ARG_SPECS.get(name)
    formatted = []
    if spec is None:
        # Raw fallback: decimal registers, trailing zeroes dropped.
        raw = list(args)
        while raw and raw[-1] == 0:
            raw.pop()
        formatted = [str(to_signed(v)) for v in raw]
    else:
        for index, descriptor in enumerate(spec):
            value = args[index]
            if ("arg", index) in entry_cache:
                formatted.append(entry_cache[("arg", index)])
                continue
            if isinstance(descriptor, tuple):
                kind, count_index = descriptor
                if "buf" in entry_cache:
                    formatted.append(entry_cache["buf"])
                    continue
                count = args[count_index]
                if mem is None:
                    formatted.append("0x%x" % value)
                    continue
                data = mem.memory(value, count)
                formatted.append(format_c_bytes(data)
                                 if data is not None else "0x%x" % value)
                continue
            # faccessat flags are omitted when 0 (real strace style,
            # matching the page's faccessat example with 3 arguments).
            if descriptor == "atflags" and value == 0:
                continue
            # open/openat mode is only shown when O_CREAT is set.
            if descriptor == "mode" and name in ("open", "openat"):
                flags = args[1] if name == "open" else args[2]
                if not (flags & 0o100):
                    continue
            formatted.append(_format_arg(descriptor, value, args, mem,
                                         entry_cache))
    if ret is None:
        ret_text = "?"
    else:
        ret_text = format_return(name, ret)
    return "%s(%s) = %s" % (name, ", ".join(formatted), ret_text)


# ---------------------------------------------------------------------------
# -c statistics
# ---------------------------------------------------------------------------

class SyscallStats:
    def __init__(self):
        self.data = {}

    def record(self, name, elapsed, ret):
        entry = self.data.setdefault(name, [0, 0, 0.0])
        entry[0] += 1
        if ret is not None and -4096 < ret < 0:
            entry[1] += 1
        entry[2] += elapsed

    def render(self):
        total_calls = sum(v[0] for v in self.data.values())
        total_errors = sum(v[1] for v in self.data.values())
        total_seconds = sum(v[2] for v in self.data.values())
        lines = [
            "% time     seconds  usecs/call     calls    errors syscall",
            "------ ----------- ----------- --------- --------- ----------------",
        ]
        for name, (calls, errors, seconds) in sorted(
                self.data.items(), key=lambda kv: (-kv[1][2], kv[0])):
            percent = (100.0 * seconds / total_seconds) if total_seconds else 0.0
            usecs = int(seconds * 1e6 / calls) if calls else 0
            lines.append("%6.2f %11.6f %11d %9d %9d %s" % (
                percent, seconds, usecs, calls, errors, name))
        lines.append(
            "------ ----------- ----------- --------- --------- ----------------")
        lines.append("%6.2f %11.6f %11s %9d %9d total" % (
            100.00, total_seconds, "", total_calls, total_errors))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reading child memory
# ---------------------------------------------------------------------------

class ChildMemory:
    """Reads a tracee's memory via PTRACE_PEEKDATA. Read-only."""

    def __init__(self, pid):
        self.pid = pid

    def _peek_word(self, addr):
        result, err = _ptrace(PTRACE_PEEKDATA, self.pid, addr, 0)
        if result == -1 and err != 0:
            return None
        return result & ((1 << 64) - 1)

    def memory(self, addr, length):
        if addr == 0 or length <= 0:
            return b"" if length == 0 else None
        out = bytearray()
        remaining = length
        current = addr
        while remaining > 0:
            word = self._peek_word(current)
            if word is None:
                break
            chunk = word.to_bytes(8, "little")[:min(8, remaining)]
            out.extend(chunk)
            current += 8
            remaining -= len(chunk)
        return bytes(out) if out or length == 0 else None

    def c_string(self, addr, limit=4096):
        if addr == 0:
            return None
        out = bytearray()
        current = addr
        while len(out) < limit:
            word = self._peek_word(current)
            if word is None:
                return bytes(out) if out else None
            chunk = word.to_bytes(8, "little")
            nul = chunk.find(b"\x00")
            if nul >= 0:
                out.extend(chunk[:nul])
                return bytes(out)
            out.extend(chunk)
            current += 8
        return bytes(out)

    def _pointer_array(self, addr, limit=10000):
        if addr == 0:
            return None
        pointers = []
        current = addr
        while len(pointers) < limit:
            word = self._peek_word(current)
            if word is None:
                return pointers if pointers else None
            if word == 0:
                return pointers
            pointers.append(word)
            current += 8
        return pointers

    def argv(self, addr):
        pointers = self._pointer_array(addr)
        if pointers is None:
            return None
        result = []
        for pointer in pointers:
            text = self.c_string(pointer)
            result.append(text if text is not None else b"")
        return result

    def envp_count(self, addr):
        pointers = self._pointer_array(addr)
        return None if pointers is None else len(pointers)

    def stat(self, addr):
        data = self.memory(addr, 64)
        if data is None or len(data) < 56:
            return None
        import struct as _struct
        mode = _struct.unpack_from("<I", data, 24)[0]
        size = _struct.unpack_from("<q", data, 48)[0]
        return (mode, size)


# ---------------------------------------------------------------------------
# Tracer loop
# ---------------------------------------------------------------------------

def _signal_name(sig):
    return _SIGNAL_NAMES.get(sig, "SIG%d" % sig)


def trace(command, count_only, out):
    """Trace command. Returns the child's exit status (128+sig on signal)."""
    if sys.platform != "linux" or platform.machine() not in ("x86_64", "AMD64"):
        out.write("strace: this tracer supports Linux x86_64 only\n")
        return 2
    pid = os.fork()
    if pid == 0:
        # Child: become traceable, stop, then exec.
        try:
            _ptrace(PTRACE_TRACEME, 0, 0, 0)
            os.kill(os.getpid(), signal.SIGSTOP)
            os.execvp(command[0], command)
        except OSError as exc:
            os.write(2, ("strace: %s: %s\n" % (command[0], exc)).encode())
        os._exit(127)

    mem = ChildMemory(pid)
    stats = SyscallStats()
    try:
        _, status = os.waitpid(pid, 0)
    except ChildProcessError:
        return 1
    if os.WIFEXITED(status) or os.WIFSIGNALED(status):
        # Child died before the first stop (e.g. exec failed hard).
        return os.WEXITSTATUS(status) if os.WIFEXITED(status) else 128

    result, err = _ptrace(PTRACE_SETOPTIONS, pid, 0, PTRACE_O_TRACESYSGOOD)
    if result == -1 and err != 0:
        out.write("strace: ptrace failed: %s\n" % os.strerror(err))
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except OSError:
            pass
        return 1

    in_syscall = False
    pending = None  # (name, args, start, entry_cache)
    deliver = 0
    exit_code = 0
    while True:
        result, err = _ptrace(PTRACE_SYSCALL, pid, 0, deliver)
        if result == -1 and err != 0:
            out.write("strace: ptrace failed: %s\n" % os.strerror(err))
            return 1
        deliver = 0
        try:
            _, status = os.waitpid(pid, 0)
        except ChildProcessError:
            break
        if os.WIFEXITED(status):
            exit_code = os.WEXITSTATUS(status)
            if pending is not None and pending[0] in ("exit", "exit_group"):
                if not count_only:
                    out.write("%s\n" % format_call(
                        pending[0], pending[1], None, mem, pending[3]))
                stats.record(pending[0], time.monotonic() - pending[2], None)
            if not count_only:
                out.write("+++ exited with %d +++\n" % exit_code)
            break
        if os.WIFSIGNALED(status):
            sig = os.WTERMSIG(status)
            exit_code = 128 + sig
            if not count_only:
                out.write("+++ killed by %s +++\n" % _signal_name(sig))
            break
        if not os.WIFSTOPPED(status):
            continue
        sig = os.WSTOPSIG(status)
        if sig == (signal.SIGTRAP | 0x80):
            regs = Regs()
            result, err = _ptrace(PTRACE_GETREGS, pid, 0, ctypes.byref(regs))
            if result == -1 and err != 0:
                out.write("strace: ptrace failed: %s\n" % os.strerror(err))
                return 1
            args = (regs.rdi, regs.rsi, regs.rdx, regs.r10, regs.r8, regs.r9)
            if not in_syscall:
                name = syscall_name(regs.orig_rax)
                entry_cache = {}
                # Capture path/argv/envp at entry: after a successful
                # execve the old image (and its strings) is gone, so
                # these must not be re-read at exit.
                spec_entry = ARG_SPECS.get(name)
                if spec_entry:
                    for _i, _desc in enumerate(spec_entry):
                        if _desc in ("path", "argv", "envp"):
                            entry_cache[("arg", _i)] = _format_arg(
                                _desc, args[_i], args, mem, entry_cache)
                if name in WRITE_FAMILY:
                    spec = ARG_SPECS.get(name)
                    if spec:
                        for index, descriptor in enumerate(spec):
                            if isinstance(descriptor, tuple):
                                data = mem.memory(args[index], args[descriptor[1]])
                                entry_cache["buf"] = (
                                    format_c_bytes(data) if data is not None
                                    else "0x%x" % args[index])
                                break
                pending = (name, args, time.monotonic(), entry_cache)
                in_syscall = True
            else:
                name, entry_args, start, entry_cache = pending
                ret = to_signed(regs.rax)
                elapsed = time.monotonic() - start
                stats.record(name, elapsed, ret)
                if not count_only:
                    out.write("%s\n" % format_call(
                        name, entry_args, ret, mem, entry_cache))
                pending = None
                in_syscall = False
        elif sig in (signal.SIGSTOP, signal.SIGTRAP):
            # Initial stop, and the SIGTRAP the kernel sends after a
            # successful execve in a traced process: both are tracer
            # artefacts, not signals for the child. Resume with 0;
            # forwarding the exec SIGTRAP would kill the child.
            deliver = 0
        else:
            # Genuine signal: forward it so the child sees it.
            deliver = sig
    if count_only:
        out.write(stats.render() + "\n")
    return exit_code


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

USAGE = "usage: strace.py [-c] [--] command [args...]\n"


def parse_args(argv):
    """Returns (count_only, command) or raises SystemExit(2) on error."""
    count_only = False
    command = []
    index = 0
    saw_separator = False
    while index < len(argv):
        arg = argv[index]
        if not saw_separator and arg == "--":
            saw_separator = True
        elif not saw_separator and arg == "-c":
            count_only = True
        elif not saw_separator and arg in ("-h", "--help"):
            sys.stdout.write(USAGE)
            raise SystemExit(0)
        elif not saw_separator and arg.startswith("-") and arg != "-":
            sys.stderr.write("strace: unknown option: %s\n%s" % (arg, USAGE))
            raise SystemExit(2)
        else:
            command = argv[index:]
            break
        index += 1
    if not command:
        sys.stderr.write(USAGE)
        raise SystemExit(2)
    return count_only, command


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    try:
        count_only, command = parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return trace(command, count_only, sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
