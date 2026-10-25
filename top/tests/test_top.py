#!/usr/bin/env python3
"""Tests for top.py — all against fake /proc trees, plus a live smoke test."""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import top as topmod
from top import (SnapshotError, compute_cpu_percent, count_tasks,
                 cpu_percentages, filter_processes, format_snapshot,
                 format_time_plus, format_uptime, parse_cpu_totals,
                 parse_meminfo, parse_stat_line, read_processes, snapshot,
                 sort_processes)

TOP_PY = os.path.join(os.path.dirname(__file__), "..", "top.py")

MEMINFO = (
    "MemTotal:        8000000 kB\n"
    "MemFree:         2000000 kB\n"
    "MemAvailable:    4000000 kB\n"
    "Buffers:          500000 kB\n"
    "Cached:          1000000 kB\n"
    "SwapTotal:       1000000 kB\n"
    "SwapFree:        1000000 kB\n"
)

CPU_STAT = "cpu  1000 100 500 8000 100 10 20 0 0 0\n"


def stat_line(pid, comm, state="S", utime=100, stime=50, pr=20, ni=0,
              threads=1, vsize=1024000, rss=1000):
    """Build a /proc/<pid>/stat line with exactly 24 fields."""
    fields = [state, "1", "1", "1", "0", "-1",  # state..tpgid
              "0", "0", "0", "0", "0",          # flags..cmajflt
              str(utime), str(stime), "0", "0",  # utime..cstime
              str(pr), str(ni), str(threads), "0", "100",  # pr..starttime
              str(vsize), str(rss)]             # vsize, rss
    assert len(fields) == 22, len(fields)
    return f"{pid} ({comm}) " + " ".join(fields) + "\n"


def make_tree(root, procs, meminfo=MEMINFO, cpu_stat=CPU_STAT,
              uptime="90061.0 1000.0", loadavg="0.10 0.20 0.30 1/50 123\n"):
    """procs: list of dicts with pid/comm/state/uid/utime/... keys."""
    with open(os.path.join(root, "meminfo"), "w") as fh:
        fh.write(meminfo)
    with open(os.path.join(root, "stat"), "w") as fh:
        fh.write(cpu_stat)
    with open(os.path.join(root, "uptime"), "w") as fh:
        fh.write(uptime)
    with open(os.path.join(root, "loadavg"), "w") as fh:
        fh.write(loadavg)
    for proc in procs:
        d = os.path.join(root, str(proc["pid"]))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "stat"), "w") as fh:
            fh.write(stat_line(
                proc["pid"], proc.get("comm", f"proc{proc['pid']}"),
                state=proc.get("state", "S"),
                utime=proc.get("utime", 100), stime=proc.get("stime", 50),
                pr=proc.get("pr", 20), ni=proc.get("ni", 0),
                threads=proc.get("threads", 1),
                vsize=proc.get("vsize", 1024000),
                rss=proc.get("rss", 1000)))
        if proc.get("status", True):
            with open(os.path.join(d, "status"), "w") as fh:
                uid = proc.get("uid", 0)
                fh.write(f"Name:\tproc{proc['pid']}\n"
                         f"Uid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
        if proc.get("statm", True):
            with open(os.path.join(d, "statm"), "w") as fh:
                fh.write("250 250 50 0 0 0 0\n")
    return root


class TestParsing(unittest.TestCase):
    def test_parse_stat_normal(self):
        parsed = parse_stat_line(stat_line(42, "bash", utime=120, stime=30))
        self.assertEqual(parsed["pid"], 42)
        self.assertEqual(parsed["command"], "bash")
        self.assertEqual(parsed["state"], "S")
        self.assertEqual(parsed["utime"], 120)
        self.assertEqual(parsed["stime"], 30)
        self.assertEqual(parsed["vsize"], 1024000)
        self.assertEqual(parsed["rss_pages"], 1000)

    def test_parse_stat_comm_with_spaces_and_parens(self):
        parsed = parse_stat_line(stat_line(7, "my (cool) proc"))
        self.assertEqual(parsed["command"], "my (cool) proc")
        self.assertEqual(parsed["pid"], 7)

    def test_parse_stat_malformed_raises(self):
        with self.assertRaises(ValueError):
            parse_stat_line("123 no parens here\n")
        with self.assertRaises(ValueError):
            parse_stat_line("123 (x)  S\n")

    def test_parse_meminfo(self):
        info = parse_meminfo(MEMINFO)
        self.assertEqual(info["MemTotal"], 8000000)
        self.assertEqual(info["MemAvailable"], 4000000)
        self.assertEqual(info["SwapFree"], 1000000)

    def test_parse_cpu_totals(self):
        totals = parse_cpu_totals(CPU_STAT)
        self.assertEqual(totals["user"], 1000)
        self.assertEqual(totals["idle"], 8000)
        self.assertEqual(totals["iowait"], 100)

    def test_parse_cpu_totals_missing_raises(self):
        with self.assertRaises(ValueError):
            parse_cpu_totals("intr 0\n")


class TestCpuMath(unittest.TestCase):
    def test_compute_cpu_percent_exact(self):
        self.assertAlmostEqual(compute_cpu_percent(100, 200, 1.0, 100), 100.0)
        self.assertAlmostEqual(compute_cpu_percent(0, 50, 2.0, 100), 25.0)

    def test_compute_cpu_percent_zero_delay_is_zero(self):
        self.assertEqual(compute_cpu_percent(0, 999, 0, 100), 0.0)

    def test_compute_cpu_percent_negative_clamped(self):
        self.assertEqual(compute_cpu_percent(200, 100, 1.0, 100), 0.0)

    def test_cpu_percentages_delta(self):
        prev = parse_cpu_totals("cpu  100 0 100 700 0 0 0 0 0 0\n")
        curr = parse_cpu_totals("cpu  200 0 100 800 0 0 0 0 0 0\n")
        pct = cpu_percentages(prev, curr)
        self.assertAlmostEqual(pct["us"], 50.0)
        self.assertAlmostEqual(pct["id"], 50.0)
        self.assertAlmostEqual(pct["sy"], 0.0)
        self.assertAlmostEqual(sum(pct.values()), 100.0)

    def test_cpu_percentages_zero_delta_is_all_idle(self):
        totals = parse_cpu_totals(CPU_STAT)
        pct = cpu_percentages(totals, totals)
        self.assertEqual(pct["id"], 100.0)
        self.assertEqual(pct["us"], 0.0)


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_tree(self.tmp.name, [
            {"pid": 1, "comm": "init", "state": "S", "uid": 0,
             "utime": 100, "stime": 50, "rss": 1000},
            {"pid": 2, "comm": "worker", "state": "R", "uid": 1000,
             "utime": 200, "stime": 100, "rss": 2000},
            {"pid": 3, "comm": "zombie", "state": "Z", "uid": 0,
             "utime": 0, "stime": 0, "rss": 0},
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_fields(self):
        snap = snapshot(self.root, 0)
        self.assertEqual(len(snap.processes), 3)
        by_pid = {p.pid: p for p in snap.processes}
        self.assertEqual(by_pid[1].command, "init")
        self.assertEqual(by_pid[1].user, "root")
        self.assertEqual(by_pid[2].user, "1000")  # unresolvable UID fallback
        self.assertEqual(by_pid[1].virt_kb, 1000)  # 1024000 // 1024
        self.assertEqual(by_pid[1].res_kb, 1000 * 4)  # 1000 pages * 4 KiB
        self.assertEqual(by_pid[1].shr_kb, 50 * 4)
        self.assertEqual(by_pid[1].cpu_percent, 0.0)  # delay 0: no rate
        self.assertEqual(snap.user_count, 2)
        self.assertEqual(snap.mem_total_kb, 8000000)
        self.assertEqual(snap.mem_used_kb, 8000000 - 2000000 - 1500000)
        self.assertEqual(snap.mem_avail_kb, 4000000)

    def test_mem_percent(self):
        snap = snapshot(self.root, 0)
        by_pid = {p.pid: p for p in snap.processes}
        # res 4000 KiB / 8000000 KiB * 100
        self.assertAlmostEqual(by_pid[1].mem_percent, 0.05)
        self.assertAlmostEqual(by_pid[2].mem_percent, 0.10)

    def test_task_counts(self):
        snap = snapshot(self.root, 0)
        self.assertEqual(snap.task_counts,
                         {"total": 3, "running": 1, "sleeping": 1,
                          "stopped": 0, "zombie": 1})

    def test_count_tasks_all_states(self):
        class P:
            def __init__(self, state):
                self.state = state
        counts = count_tasks([P(s) for s in "RSDITZtX"])
        self.assertEqual(counts["running"], 1)
        self.assertEqual(counts["sleeping"], 3)  # S, D, I
        self.assertEqual(counts["stopped"], 2)   # T, t
        self.assertEqual(counts["zombie"], 2)    # Z, X
        self.assertEqual(counts["total"], 8)

    def test_missing_status_user_is_question_mark(self):
        with tempfile.TemporaryDirectory() as root:
            make_tree(root, [{"pid": 9, "comm": "ghost", "status": False}])
            procs = read_processes(root)
            self.assertEqual(procs[0].user, "?")
            self.assertIsNone(procs[0].uid)

    def test_missing_statm_shr_zero(self):
        with tempfile.TemporaryDirectory() as root:
            make_tree(root, [{"pid": 9, "comm": "bare", "statm": False}])
            procs = read_processes(root)
            self.assertEqual(procs[0].shr_kb, 0)

    def test_missing_meminfo_raises(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "stat"), "w") as fh:
                fh.write(CPU_STAT)
            with self.assertRaises(SnapshotError):
                snapshot(root, 0)

    def test_missing_proc_root_raises(self):
        with self.assertRaises(SnapshotError):
            snapshot("/nonexistent-proc-root-xyz", 0)

    def test_missing_memavailable_falls_back_to_free(self):
        meminfo = ("MemTotal: 8000000 kB\nMemFree: 2000000 kB\n"
                   "Buffers: 0 kB\nCached: 0 kB\n"
                   "SwapTotal: 0 kB\nSwapFree: 0 kB\n")
        with tempfile.TemporaryDirectory() as root:
            make_tree(root, [{"pid": 1}], meminfo=meminfo)
            snap = snapshot(root, 0)
            self.assertEqual(snap.mem_avail_kb, 2000000)

    def test_snapshot_with_delay_measures_cpu(self):
        # Rewrite the tree on sleep() so sample 2 differs from sample 1.
        def rewrite(*_args):
            make_tree(self.root, [
                {"pid": 1, "comm": "init", "uid": 0,
                 "utime": 200, "stime": 50, "rss": 1000},
            ], cpu_stat="cpu  1100 100 500 8000 100 10 20 0 0 0\n")

        with mock.patch.object(topmod.time, "sleep", side_effect=rewrite):
            snap = snapshot(self.root, 1.0)
        proc = {p.pid: p for p in snap.processes}[1]
        # (250 - 150) ticks / (100 ticks/s * 1 s) * 100 = 100.0
        self.assertAlmostEqual(proc.cpu_percent, 100.0)
        # Header: user delta 100 of total delta 100 -> 100% us
        self.assertAlmostEqual(snap.cpu["us"], 100.0)


class TestSortFilterFormat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_tree(self.tmp.name, [
            {"pid": 30, "comm": "zeta", "uid": 0, "utime": 10, "stime": 0,
             "rss": 500},
            {"pid": 10, "comm": "alpha", "uid": 0, "utime": 900, "stime": 0,
             "rss": 3000},
            {"pid": 20, "comm": "mid", "uid": 1000, "utime": 10, "stime": 0,
             "rss": 500},
        ])
        self.snap = snapshot(self.root, 0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sort_pid_default_ascending(self):
        self.assertEqual([p.pid for p in sort_processes(self.snap.processes, "pid")],
                         [10, 20, 30])

    def test_sort_mem_descending_tie_breaks_by_pid(self):
        # pid 20 and 30 have equal RSS; pid 10 has the largest.
        order = [p.pid for p in sort_processes(self.snap.processes, "mem")]
        self.assertEqual(order, [10, 20, 30])

    def test_sort_command_ascending(self):
        order = [p.command for p in sort_processes(self.snap.processes, "command")]
        self.assertEqual(order, ["alpha", "mid", "zeta"])

    def test_sort_time_descending(self):
        order = [p.pid for p in sort_processes(self.snap.processes, "time")]
        self.assertEqual(order[0], 10)

    def test_unknown_sort_key_raises(self):
        with self.assertRaises(ValueError):
            sort_processes(self.snap.processes, "bogus")

    def test_filter_by_username(self):
        rows = filter_processes(self.snap.processes, user="root")
        self.assertEqual(sorted(p.pid for p in rows), [10, 30])

    def test_filter_by_numeric_uid(self):
        rows = filter_processes(self.snap.processes, user="1000")
        self.assertEqual([p.pid for p in rows], [20])

    def test_filter_by_pid(self):
        rows = filter_processes(self.snap.processes, pids=[20])
        self.assertEqual([p.pid for p in rows], [20])

    def test_filter_no_match_empty_table(self):
        rows = filter_processes(self.snap.processes, user="nobody-here")
        self.assertEqual(rows, [])

    def test_format_snapshot_labels_and_row(self):
        text = format_snapshot(self.snap, self.snap.processes)
        self.assertIn("Tasks:", text)
        self.assertIn("%Cpu(s):", text)
        self.assertIn("MiB Mem :", text)
        self.assertIn("MiB Swap:", text)
        self.assertIn("COMMAND", text)
        line10 = [ln for ln in text.splitlines() if "alpha" in ln][0]
        self.assertIn("10", line10.split()[0])
        self.assertIn("root", line10)

    def test_format_limit_truncates(self):
        rows = sort_processes(self.snap.processes, "pid")
        text = format_snapshot(self.snap, rows, limit=1)
        self.assertEqual(len([ln for ln in text.splitlines()
                              if "alpha" in ln or "mid" in ln
                              or "zeta" in ln]), 1)

    def test_format_time_plus(self):
        self.assertEqual(format_time_plus(65.25), "1:05.25")
        self.assertEqual(format_time_plus(3661), "1:01:01")

    def test_format_uptime(self):
        self.assertEqual(format_uptime(90061), "1 day, 1:01")
        self.assertEqual(format_uptime(3661), "1:01")
        self.assertEqual(format_uptime(300), "5 min")


class TestCLI(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, TOP_PY, *args],
            capture_output=True, text=True, timeout=30)

    def test_cli_batch_one_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            make_tree(root, [{"pid": 1, "comm": "init", "uid": 0}])
            result = self.run_cli("-b", "-n", "1", "-d", "0",
                                  "--proc-root", root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Tasks:", result.stdout)
            self.assertIn("init", result.stdout)
            self.assertEqual(result.stdout.count("top - "), 1)

    def test_cli_batch_two_snapshots(self):
        with tempfile.TemporaryDirectory() as root:
            make_tree(root, [{"pid": 1, "comm": "init", "uid": 0}])
            result = self.run_cli("-b", "-n", "2", "-d", "0",
                                  "--proc-root", root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count("top - "), 2)

    def test_cli_sort_cpu_and_user_filter(self):
        with tempfile.TemporaryDirectory() as root:
            make_tree(root, [{"pid": 1, "comm": "init", "uid": 0},
                             {"pid": 2, "comm": "other", "uid": 1000}])
            result = self.run_cli("-b", "-n", "1", "-d", "0", "-o", "cpu",
                                  "-u", "root", "--proc-root", root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("init", result.stdout)
            self.assertNotIn("other", result.stdout)

    def test_cli_unknown_sort_key_exits_2(self):
        result = self.run_cli("-b", "-o", "bogus")
        self.assertEqual(result.returncode, 2)

    def test_cli_missing_proc_root_exits_2(self):
        result = self.run_cli("-b", "-n", "1", "-d", "0",
                              "--proc-root", "/nonexistent-proc-root-xyz")
        self.assertEqual(result.returncode, 2)
        self.assertIn("top:", result.stderr)

    def test_no_signal_sending_code(self):
        with open(TOP_PY) as fh:
            source = fh.read()
        self.assertNotIn("os.kill", source)
        self.assertNotIn("signal.SIGKILL", source)
        self.assertNotIn("signal.SIGTERM", source)

    def test_live_smoke(self):
        result = self.run_cli("-b", "-n", "1", "-d", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Tasks:", result.stdout)
        self.assertIn("COMMAND", result.stdout)


if __name__ == "__main__":
    unittest.main()
