#!/usr/bin/env python3
"""Build Your Own Top — a live process monitor reading /proc.

Python 3 standard library only. No psutil, no shelling out to top/ps.
Batch mode (-b) prints plain text and is the headlessly testable mode;
without -b and on a TTY, a curses UI is used (not headlessly tested).

Usage:
    python3 top.py [-b] [-n N] [-d SECONDS] [-o KEY] [-u USER]
                   [-p PID,...] [--limit N] [--proc-root DIR]
"""

import argparse
import os
import pwd
import sys
import time
from dataclasses import dataclass, field


class SnapshotError(Exception):
    """Raised when the /proc tree cannot be read at all."""


# ---------------------------------------------------------------- data

@dataclass
class Process:
    pid: int
    user: str
    uid: object = None  # int, or None when /proc/<pid>/status unreadable
    pr: int = 0
    ni: int = 0
    virt_kb: int = 0
    res_kb: int = 0
    shr_kb: int = 0
    state: str = "?"
    cpu_ticks: int = 0
    cpu_percent: float = 0.0
    mem_percent: float = 0.0
    time_seconds: float = 0.0
    command: str = ""


@dataclass
class Snapshot:
    processes: list
    mem_total_kb: int = 0
    mem_free_kb: int = 0
    mem_used_kb: int = 0
    mem_buffcache_kb: int = 0
    mem_avail_kb: int = 0
    swap_total_kb: int = 0
    swap_free_kb: int = 0
    swap_used_kb: int = 0
    loadavg: tuple = (0.0, 0.0, 0.0)
    uptime_seconds: float = 0.0
    cpu: dict = field(default_factory=dict)  # us,sy,ni,id,wa,hi,si,st
    user_count: int = 0
    task_counts: dict = field(default_factory=dict)  # total,running,sleeping,stopped,zombie


# ------------------------------------------------------------ /proc parsing

def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def parse_stat_line(text):
    """Parse one /proc/<pid>/stat line -> dict.

    comm may contain spaces or parentheses, so it is taken as the text
    between the first '(' and the last ')'.
    """
    text = text.strip()
    open_paren = text.find("(")
    close_paren = text.rfind(")")
    if open_paren < 0 or close_paren < 0 or close_paren <= open_paren:
        raise ValueError("malformed stat line: no comm parentheses")
    pid = int(text[:open_paren].strip())
    command = text[open_paren + 1:close_paren]
    rest = text[close_paren + 1:].split()
    # rest[0] is field 3 (state); field N is rest[N - 3].
    if len(rest) < 22:
        raise ValueError("malformed stat line: too few fields")

    def _int(idx):
        return int(rest[idx])

    return {
        "pid": pid,
        "command": command,
        "state": rest[0],
        "utime": _int(11),   # field 14
        "stime": _int(12),   # field 15
        "priority": _int(15),  # field 18
        "nice": _int(16),    # field 19
        "vsize": _int(20),   # field 23
        "rss_pages": _int(21),  # field 24
    }


def parse_meminfo(text):
    """Parse /proc/meminfo text -> dict of kB values."""
    info = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(":"):
            try:
                info[parts[0][:-1]] = int(parts[1])
            except ValueError:
                continue
    return info


def parse_cpu_totals(text):
    """Parse the first 'cpu ' line of /proc/stat -> dict of raw ticks."""
    for line in text.splitlines():
        if line.startswith("cpu "):
            fields = line.split()[1:]
            names = ["user", "nice", "system", "idle", "iowait",
                     "irq", "softirq", "steal", "guest", "guest_nice"]
            totals = {}
            for i, name in enumerate(names):
                totals[name] = int(fields[i]) if i < len(fields) else 0
            return totals
    raise ValueError("no 'cpu ' line in /proc/stat")


def cpu_percentages(prev, curr):
    """Header %Cpu(s) breakdown from two /proc/stat cpu-total samples.

    Guest time is already counted in user/nice, so it is excluded from
    the total to avoid double-counting. A zero delta (e.g. delay 0)
    honestly reports 100% idle.
    """
    keys = ["user", "nice", "system", "idle", "iowait",
            "irq", "softirq", "steal"]
    deltas = {k: curr.get(k, 0) - prev.get(k, 0) for k in keys}
    total = sum(deltas.values())
    if total <= 0:
        return {"us": 0.0, "sy": 0.0, "ni": 0.0, "id": 100.0,
                "wa": 0.0, "hi": 0.0, "si": 0.0, "st": 0.0}
    return {
        "us": 100.0 * deltas["user"] / total,
        "sy": 100.0 * deltas["system"] / total,
        "ni": 100.0 * deltas["nice"] / total,
        "id": 100.0 * deltas["idle"] / total,
        "wa": 100.0 * deltas["iowait"] / total,
        "hi": 100.0 * deltas["irq"] / total,
        "si": 100.0 * deltas["softirq"] / total,
        "st": 100.0 * deltas["steal"] / total,
    }


def compute_cpu_percent(prev_ticks, curr_ticks, delay, clk_tck):
    """%CPU of one CPU: tick delta over the interval, as a percent."""
    if delay <= 0 or clk_tck <= 0:
        return 0.0
    return max(0.0, (curr_ticks - prev_ticks) / (clk_tck * delay) * 100.0)


def _clk_tck():
    try:
        return os.sysconf("SC_CLK_TCK")
    except (ValueError, OSError, AttributeError):
        return 100


def _page_size():
    try:
        return os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return 4096


def _uid_and_user(proc_dir):
    """(uid, username) from /proc/<pid>/status, or (None, '?')."""
    try:
        for line in _read(os.path.join(proc_dir, "status")).splitlines():
            if line.startswith("Uid:"):
                uid = int(line.split()[1])
                try:
                    return uid, pwd.getpwuid(uid).pw_name
                except (KeyError, OverflowError):
                    return uid, str(uid)
    except OSError:
        pass
    return None, "?"


def read_processes(proc_root):
    """One full process table from proc_root (cpu_percent left at 0)."""
    page_size = _page_size()
    processes = []
    try:
        entries = os.listdir(proc_root)
    except OSError as exc:
        raise SnapshotError(f"cannot read {proc_root}: {exc}") from exc
    for name in entries:
        if not name.isdigit():
            continue
        proc_dir = os.path.join(proc_root, name)
        try:
            stat = parse_stat_line(_read(os.path.join(proc_dir, "stat")))
        except (OSError, ValueError):
            continue  # process vanished or unreadable: skip, never fatal
        try:
            shared_pages = int(_read(os.path.join(proc_dir, "statm")).split()[2])
        except (OSError, ValueError, IndexError):
            shared_pages = 0
        uid, user = _uid_and_user(proc_dir)
        clk = _clk_tck()
        ticks = stat["utime"] + stat["stime"]
        processes.append(Process(
            pid=stat["pid"], user=user, uid=uid,
            pr=stat["priority"], ni=stat["nice"],
            virt_kb=stat["vsize"] // 1024,
            res_kb=stat["rss_pages"] * page_size // 1024,
            shr_kb=shared_pages * page_size // 1024,
            state=stat["state"], cpu_ticks=ticks,
            time_seconds=ticks / clk if clk else 0.0,
            command=stat["command"],
        ))
    return processes


def count_tasks(processes):
    counts = {"total": len(processes), "running": 0, "sleeping": 0,
              "stopped": 0, "zombie": 0}
    for proc in processes:
        if proc.state == "R":
            counts["running"] += 1
        elif proc.state in ("S", "D", "I"):
            counts["sleeping"] += 1
        elif proc.state in ("T", "t"):
            counts["stopped"] += 1
        elif proc.state in ("Z", "X"):
            counts["zombie"] += 1
    return counts


def snapshot(proc_root, delay):
    """Take a snapshot; with delay > 0, %CPU is measured over it."""
    try:
        cpu1 = parse_cpu_totals(_read(os.path.join(proc_root, "stat")))
        procs1 = read_processes(proc_root)
        mem = parse_meminfo(_read(os.path.join(proc_root, "meminfo")))
    except SnapshotError:
        raise
    except (OSError, ValueError) as exc:
        raise SnapshotError(f"cannot read {proc_root}: {exc}") from exc
    if not mem:
        raise SnapshotError(f"no usable meminfo in {proc_root}")

    if delay > 0:
        time.sleep(delay)
        try:
            cpu2 = parse_cpu_totals(_read(os.path.join(proc_root, "stat")))
            procs2 = read_processes(proc_root)
        except (OSError, ValueError) as exc:
            raise SnapshotError(f"cannot read {proc_root}: {exc}") from exc
    else:
        cpu2, procs2 = cpu1, procs1

    clk = _clk_tck()
    prev_ticks = {p.pid: p.cpu_ticks for p in procs1}
    mem_total = mem.get("MemTotal", 0)
    for proc in procs2:
        proc.cpu_percent = compute_cpu_percent(
            prev_ticks.get(proc.pid, proc.cpu_ticks),
            proc.cpu_ticks, delay, clk)
        # A PID first seen in sample 2 has no previous ticks, so the
        # lookup above uses its own ticks and the percent is 0.0.
        proc.mem_percent = (100.0 * proc.res_kb / mem_total
                            if mem_total > 0 else 0.0)

    try:
        uptime = float(_read(os.path.join(proc_root, "uptime")).split()[0])
    except (OSError, ValueError, IndexError):
        uptime = 0.0
    try:
        load = tuple(float(x) for x in
                     _read(os.path.join(proc_root, "loadavg")).split()[:3])
    except (OSError, ValueError):
        load = (0.0, 0.0, 0.0)
    if len(load) < 3:
        load = load + (0.0,) * (3 - len(load))

    mem_free = mem.get("MemFree", 0)
    buffers = mem.get("Buffers", 0)
    cached = mem.get("Cached", 0)
    buffcache = buffers + cached
    swap_total = mem.get("SwapTotal", 0)
    swap_free = mem.get("SwapFree", 0)
    uids = {p.uid for p in procs2 if p.uid is not None}
    return Snapshot(
        processes=procs2,
        mem_total_kb=mem_total, mem_free_kb=mem_free,
        mem_used_kb=mem_total - mem_free - buffcache,
        mem_buffcache_kb=buffcache,
        mem_avail_kb=mem.get("MemAvailable", mem_free),
        swap_total_kb=swap_total, swap_free_kb=swap_free,
        swap_used_kb=swap_total - swap_free,
        loadavg=load, uptime_seconds=uptime,
        cpu=cpu_percentages(cpu1, cpu2),
        user_count=len(uids), task_counts=count_tasks(procs2),
    )


# ------------------------------------------------------------- sorting/filter

SORT_KEYS = {
    "pid": ("pid", False),
    "user": ("user", False),
    "command": ("command", False),
    "cpu": ("cpu_percent", True),
    "mem": ("mem_percent", True),
    "time": ("time_seconds", True),
    "virt": ("virt_kb", True),
    "res": ("res_kb", True),
}


def sort_processes(processes, sort_key):
    if sort_key not in SORT_KEYS:
        raise ValueError(
            f"unknown sort key {sort_key!r} (valid: "
            + ", ".join(sorted(SORT_KEYS)) + ")")
    attr, reverse = SORT_KEYS[sort_key]
    # Ties always break by PID ascending, so order is deterministic.
    ordered = sorted(processes, key=lambda p: p.pid)
    return sorted(ordered, key=lambda p: getattr(p, attr), reverse=reverse)


def filter_processes(processes, user=None, pids=None):
    result = processes
    if user is not None:
        if user.isdigit():
            result = [p for p in result if p.uid == int(user)]
        else:
            result = [p for p in result if p.user == user]
    if pids is not None:
        wanted = set(pids)
        result = [p for p in result if p.pid in wanted]
    return result


# --------------------------------------------------------------- formatting

def format_uptime(seconds):
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        noun = "day" if days == 1 else "days"
        return f"{days} {noun}, {hours}:{minutes:02d}"
    if hours:
        return f"{hours}:{minutes:02d}"
    return f"{minutes} min"


def format_time_plus(seconds):
    if seconds >= 3600:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes}:{secs:05.2f}"


def format_snapshot(snap, processes=None, limit=None):
    if processes is None:
        processes = snap.processes
    if limit is not None:
        processes = processes[:limit]
    now = time.strftime("%H:%M:%S", time.localtime())
    counts = snap.task_counts
    cpu = snap.cpu
    lines = [
        f"top - {now} up {format_uptime(snap.uptime_seconds)}, "
        f"{snap.user_count} user{'s' if snap.user_count != 1 else ''}, "
        f"load average: {snap.loadavg[0]:.2f}, {snap.loadavg[1]:.2f}, "
        f"{snap.loadavg[2]:.2f}",
        f"Tasks: {counts['total']:3d} total, {counts['running']:3d} running, "
        f"{counts['sleeping']:3d} sleeping, {counts['stopped']:3d} stopped, "
        f"{counts['zombie']:3d} zombie",
        f"%Cpu(s): {cpu.get('us', 0.0):5.1f} us, {cpu.get('sy', 0.0):5.1f} sy, "
        f"{cpu.get('ni', 0.0):5.1f} ni, {cpu.get('id', 0.0):5.1f} id, "
        f"{cpu.get('wa', 0.0):5.1f} wa, {cpu.get('hi', 0.0):5.1f} hi, "
        f"{cpu.get('si', 0.0):5.1f} si, {cpu.get('st', 0.0):5.1f} st",
        f"MiB Mem : {snap.mem_total_kb / 1024:8.1f} total, "
        f"{snap.mem_free_kb / 1024:8.1f} free, "
        f"{snap.mem_used_kb / 1024:8.1f} used, "
        f"{snap.mem_buffcache_kb / 1024:8.1f} buff/cache",
        f"MiB Swap: {snap.swap_total_kb / 1024:8.1f} total, "
        f"{snap.swap_free_kb / 1024:8.1f} free, "
        f"{snap.swap_used_kb / 1024:8.1f} used. "
        f"{snap.mem_avail_kb / 1024:8.1f} avail Mem",
        f"{'PID':>7} {'USER':<8} {'PR':>3} {'NI':>3} {'VIRT':>8} "
        f"{'RES':>6} {'SHR':>6} {'S':>1} {'%CPU':>5} {'%MEM':>5} "
        f"{'TIME+':>9} COMMAND",
    ]
    for proc in processes:
        lines.append(
            f"{proc.pid:7d} {proc.user[:8]:<8} {proc.pr:3d} {proc.ni:3d} "
            f"{proc.virt_kb:8d} {proc.res_kb:6d} {proc.shr_kb:6d} "
            f"{proc.state:>1} {proc.cpu_percent:5.1f} {proc.mem_percent:5.1f} "
            f"{format_time_plus(proc.time_seconds):>9} {proc.command}")
    return "\n".join(lines)


# -------------------------------------------------------------------- CLI

def build_parser():
    parser = argparse.ArgumentParser(
        description="Display sorted information about processes "
                    "(reads /proc; Python stdlib only).")
    parser.add_argument("-b", "--batch", action="store_true",
                        help="batch mode: plain-text output, no curses")
    parser.add_argument("-n", "--iterations", type=int, default=None,
                        help="number of refreshes (default: run until stopped)")
    parser.add_argument("-d", "--delay", type=float, default=3.0,
                        help="seconds between refreshes (default 3.0)")
    parser.add_argument("-o", "--sort", default="pid",
                        choices=sorted(SORT_KEYS),
                        help="sort key (default: pid)")
    parser.add_argument("-u", "--user", default=None,
                        help="show only this username or numeric UID")
    parser.add_argument("-p", "--pid", default=None,
                        help="comma-separated PIDs to show")
    parser.add_argument("--limit", type=int, default=None,
                        help="maximum table rows to show")
    parser.add_argument("--proc-root", default="/proc",
                        help="proc tree to read (default /proc; "
                             "a fake tree is used by the test suite)")
    return parser


def _parse_pids(value):
    if value is None:
        return None
    try:
        return [int(x) for x in value.split(",") if x != ""]
    except ValueError:
        raise SystemExit(f"top: invalid --pid value {value!r}")


def run_batch(args, out):
    pids = _parse_pids(args.pid)
    iteration = 0
    while args.iterations is None or iteration < args.iterations:
        snap = snapshot(args.proc_root, args.delay)
        rows = sort_processes(
            filter_processes(snap.processes, user=args.user, pids=pids),
            args.sort)
        out.write(format_snapshot(snap, rows, limit=args.limit) + "\n")
        out.flush()
        iteration += 1
        if args.iterations is None or iteration < args.iterations:
            out.write("\n")
    return 0


def run_interactive(args):
    """Curses loop. Thin wrapper over snapshot/format; NOT headlessly tested."""
    try:
        import curses
    except ImportError:
        print("top: curses unavailable, falling back to one batch snapshot",
              file=sys.stderr)
        args.batch = True
        return run_batch_once(args)
    sort_key = args.sort
    message = ""

    def loop(stdscr):
        nonlocal sort_key, message
        curses.curs_set(0)
        stdscr.nodelay(True)
        iteration = 0
        while args.iterations is None or iteration < args.iterations:
            snap = snapshot(args.proc_root, args.delay)
            rows = sort_processes(
                filter_processes(snap.processes, user=args.user,
                                 pids=_parse_pids(args.pid)), sort_key)
            text = format_snapshot(snap, rows, limit=args.limit)
            stdscr.erase()
            for i, line in enumerate(text.splitlines()):
                if i >= curses.LINES - 1:
                    break
                try:
                    stdscr.addstr(i, 0, line[:curses.COLS - 1])
                except curses.error:
                    pass
            if message and curses.LINES > 1:
                try:
                    stdscr.addstr(curses.LINES - 1, 0,
                                  message[:curses.COLS - 1])
                except curses.error:
                    pass
            stdscr.refresh()
            iteration += 1
            deadline = time.time() + args.delay
            key = -1
            while time.time() < deadline:
                key = stdscr.getch()
                if key != -1:
                    break
                time.sleep(0.05)
            if key in (ord("q"), ord("Q")):
                break
            if key == ord("P"):
                sort_key, message = "cpu", ""
            elif key == ord("M"):
                sort_key, message = "mem", ""
            elif key == ord("N"):
                sort_key, message = "pid", ""
            elif key == ord("T"):
                sort_key, message = "time", ""
            elif key == ord("k"):
                # Guarded: kill/renice are NOT implemented (see SPEC).
                message = "kill/renice not supported in this build"

    try:
        curses.wrapper(loop)
    except Exception as exc:  # no TTY / bad TERM: degrade, don't crash
        print(f"top: interactive display failed ({exc}), "
              "falling back to one batch snapshot", file=sys.stderr)
        return run_batch_once(args)
    return 0


def run_batch_once(args):
    """One batch snapshot, used as the interactive fallback."""
    snap = snapshot(args.proc_root, 0)
    rows = sort_processes(
        filter_processes(snap.processes, user=args.user,
                         pids=_parse_pids(args.pid)), args.sort)
    print(format_snapshot(snap, rows, limit=args.limit))
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.delay < 0:
        print("top: --delay must not be negative", file=sys.stderr)
        return 2
    if args.iterations is not None and args.iterations < 0:
        print("top: --iterations must not be negative", file=sys.stderr)
        return 2
    if args.limit is not None and args.limit < 0:
        print("top: --limit must not be negative", file=sys.stderr)
        return 2
    try:
        if args.batch or not sys.stdout.isatty():
            return run_batch(args, sys.stdout)
        return run_interactive(args)
    except SnapshotError as exc:
        print(f"top: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
