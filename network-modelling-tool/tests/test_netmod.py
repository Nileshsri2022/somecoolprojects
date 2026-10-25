"""Tests for netmod.py. Run: python3 -m unittest discover -s tests -v"""
import csv
import io
import itertools
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from netmod import (Demand, Link, Network, NetmodError, apply_traffic,
                    load_network, load_traffic, render_svg,
                    shortest_path, worst_case_failures, write_links_csv,
                    write_routes_csv)

ROOT = Path(__file__).resolve().parent.parent


def write_tmp(tmpdir, name, text):
    path = Path(tmpdir) / name
    path.write_text(text, encoding="utf-8")
    return path


def net_from(text):
    with tempfile.TemporaryDirectory() as tmp:
        return load_network(write_tmp(tmp, "n.csv", text))


def traffic_from(text):
    with tempfile.TemporaryDirectory() as tmp:
        return load_traffic(write_tmp(tmp, "t.csv", text))


PAGE_NETWORK = """LinkId,Start,End,Capacity,Weight
1,A,B,10,5
2,B,C,10,5
3,C,D,10,5
4,D,E,10,5
5,E,F,10,5
6,G,H,10,5
7,H,A,10,5
8,A,I,10,5
9,B,I,10,1
10,C,G,10,5
11,D,F,10,1
12,I,G,10,5
13,F,G,10,3
"""

PAGE_TRAFFIC = """Source,Destination,Demand
A,E,1
B,A,3
I,E,2
A,G,5
H,D,4
"""


def brute_shortest(network, source, dest):
    """Independent check: enumerate simple paths, min (weight, nodes)."""
    adj = network.adjacency()
    best = None
    stack = [(source, (source,), 0.0)]
    while stack:
        node, path, cost = stack.pop()
        if node == dest:
            cand = (cost, path)
            if best is None or cand < best:
                best = cand
            continue
        for nb, w, _ in adj[node]:
            if nb not in path:
                stack.append((nb, path + (nb,), cost + w))
    return best


class TestLoading(unittest.TestCase):
    def test_page_example_network(self):
        net = net_from(PAGE_NETWORK)
        self.assertEqual(len(net.nodes), 9)
        self.assertEqual(len(net.links), 13)
        by_id = {l.link_id: l for l in net.links}
        self.assertEqual((by_id["9"].start, by_id["9"].end,
                          by_id["9"].capacity, by_id["9"].weight),
                         ("B", "I", 10, 1))
        self.assertEqual((by_id["11"].start, by_id["11"].end,
                          by_id["11"].weight), ("D", "F", 1))

    def test_page_example_traffic(self):
        demands = traffic_from(PAGE_TRAFFIC)
        self.assertEqual(len(demands), 5)
        self.assertEqual(demands[0], Demand("A", "E", 1))
        self.assertEqual(demands[3], Demand("A", "G", 5))

    def test_case_insensitive_headers_and_extra_columns(self):
        net = net_from(" linkid , START,End ,Capacity,Weight,Note\n"
                       "1,X,Y,10,2,hi\n")
        self.assertEqual(net.links[0].start, "X")

    def test_load_errors(self):
        bad = {
            "missing column": "LinkId,Start,End,Capacity\n1,A,B,10\n",
            "empty": "LinkId,Start,End,Capacity,Weight\n",
            "non-numeric capacity": "LinkId,Start,End,Capacity,Weight\n1,A,B,x,5\n",
            "zero capacity": "LinkId,Start,End,Capacity,Weight\n1,A,B,0,5\n",
            "negative weight": "LinkId,Start,End,Capacity,Weight\n1,A,B,10,-1\n",
            "duplicate id": "LinkId,Start,End,Capacity,Weight\n1,A,B,10,5\n1,B,C,10,5\n",
            "self-loop": "LinkId,Start,End,Capacity,Weight\n1,A,A,10,5\n",
        }
        for name, text in bad.items():
            with self.subTest(name=name), self.assertRaises(NetmodError):
                net_from(text)

    def test_traffic_errors(self):
        with self.assertRaises(NetmodError):
            traffic_from("Source,Destination,Demand\nA,B,0\n")
        with self.assertRaises(NetmodError):
            traffic_from("Source,Destination,Demand\nA,B,soon\n")

    def test_missing_file_is_error(self):
        with self.assertRaises(NetmodError):
            load_network("/tmp/does-not-exist-netmod.csv")


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.net = net_from(PAGE_NETWORK)

    def test_page_paths(self):
        # A->D: A-H-G-F-D = 5+5+3+1 = 14, beating A-B-C-D = 15
        # and A-I-B-C-D = 5+1+5+5 = 16 (the weight-1 D-F link in
        # reverse is what makes the H route win).
        route = shortest_path(self.net, "A", "D")
        self.assertEqual(route.nodes, ("A", "H", "G", "F", "D"))
        self.assertEqual(route.total_weight, 14)
        # B->A: direct link 1 = 5, beating B-I-A = 1+5 = 6.
        route = shortest_path(self.net, "B", "A")
        self.assertEqual(route.nodes, ("B", "A"))
        self.assertEqual(route.total_weight, 5)
        # D->F: direct link 11 = 1, beating D-C-G-F = 5+5+3 = 13.
        route = shortest_path(self.net, "D", "F")
        self.assertEqual(route.nodes, ("D", "F"))
        self.assertEqual(route.link_ids, ("11",))

    def test_bidirectional(self):
        # Link 7 is listed H->A; A->H must still work, and H->A too.
        self.assertIsNotNone(shortest_path(self.net, "A", "H"))
        self.assertIsNotNone(shortest_path(self.net, "H", "A"))

    def test_all_pairs_match_brute_force(self):
        for src, dst in itertools.permutations(sorted(self.net.nodes), 2):
            route = shortest_path(self.net, src, dst)
            brute = brute_shortest(self.net, src, dst)
            self.assertIsNotNone(route, f"{src}->{dst}")
            self.assertEqual((route.total_weight, route.nodes), brute)

    def test_tie_break_lexicographic(self):
        net = net_from("LinkId,Start,End,Capacity,Weight\n"
                       "1,A,B,10,1\n2,B,D,10,1\n3,A,C,10,1\n4,C,D,10,1\n")
        route = shortest_path(net, "A", "D")
        self.assertEqual(route.nodes, ("A", "B", "D"))

    def test_parallel_links_pick_lowest_weight(self):
        net = net_from("LinkId,Start,End,Capacity,Weight\n"
                       "1,A,B,10,9\n2,A,B,10,2\n")
        route = shortest_path(net, "A", "B")
        self.assertEqual(route.link_ids, ("2",))

    def test_zero_weight_allowed(self):
        net = net_from("LinkId,Start,End,Capacity,Weight\n"
                       "1,A,B,10,0\n2,B,C,10,5\n3,A,C,10,9\n")
        self.assertEqual(shortest_path(net, "A", "C").nodes, ("A", "B", "C"))

    def test_unreachable_and_unknown(self):
        net = net_from("LinkId,Start,End,Capacity,Weight\n1,A,B,10,1\n")
        self.assertIsNone(shortest_path(net, "A", "C"))
        self.assertIsNone(shortest_path(net, "A", "ZZZ"))

    def test_same_node(self):
        route = shortest_path(self.net, "A", "A")
        self.assertTrue(route.routed)
        self.assertEqual(route.nodes, ())
        self.assertEqual(route.total_weight, 0)

    def test_exclusion_reroutes_and_disconnects(self):
        # Removing link 1 (A-B) must not break A->B: via A-I-B = 5+1.
        route = shortest_path(self.net, "A", "B",
                              excluded=frozenset({"1"}))
        self.assertEqual(route.nodes, ("A", "I", "B"))
        # Removing every A link isolates A.
        route = shortest_path(self.net, "A", "B",
                              excluded=frozenset({"1", "7", "8"}))
        self.assertIsNone(route)


class TestTraffic(unittest.TestCase):
    def setUp(self):
        self.net = net_from(PAGE_NETWORK)
        self.demands = traffic_from(PAGE_TRAFFIC)

    def test_single_demand_loads_only_its_path(self):
        result = apply_traffic(self.net, [Demand("D", "F", 4)])
        loads = {u.link.link_id: u.load for u in result.utils}
        self.assertEqual(loads["11"], 4)
        self.assertTrue(all(v == 0 for k, v in loads.items() if k != "11"))

    def test_bidirectional_loads_add(self):
        result = apply_traffic(self.net, [Demand("A", "B", 2),
                                          Demand("B", "A", 3)])
        loads = {u.link.link_id: u.load for u in result.utils}
        self.assertEqual(loads["1"], 5)

    def test_page_traffic_matches_brute_force_and_conserves(self):
        result = apply_traffic(self.net, self.demands)
        self.assertEqual(result.unroutable, 0)
        # Independent brute-force loads.
        expected = {l.link_id: 0.0 for l in self.net.links}
        adj_links = {}
        for link in self.net.links:
            adj_links.setdefault(link.start, []).append((link.end, link))
            adj_links.setdefault(link.end, []).append((link.start, link))
        for demand in self.demands:
            # Re-derive link ids from the brute-force node path.
            _, nodes = brute_shortest(self.net, demand.source,
                                      demand.destination)
            for a, b in zip(nodes, nodes[1:]):
                link_id = next(l.link_id for nb, l in adj_links[a]
                               if nb == b and (
                                   # pick the lowest-weight parallel link
                                   l.link_id == min(
                                       x.link_id for y, x in adj_links[a]
                                       if y == b and x.weight == min(
                                           z.weight for w, z in adj_links[a]
                                           if w == b))))
                expected[link_id] += demand.demand
        actual = {u.link.link_id: u.load for u in result.utils}
        self.assertEqual(actual, expected)
        # Conservation: sum of loads == sum of demand x hops.
        total = sum(u.load for u in result.utils)
        hops = sum(d.demand * (len(r.nodes) - 1)
                   for d, r in zip(self.demands, result.routes))
        self.assertEqual(total, hops)

    def test_over_capacity_flag_uncapped(self):
        result = apply_traffic(self.net, [Demand("A", "B", 15)])
        util = next(u for u in result.utils if u.link.link_id == "1")
        self.assertEqual(util.utilisation, 150.0)
        self.assertEqual(util.flag, "OVER")

    def test_threshold_flags(self):
        def flag_for(load):
            result = apply_traffic(self.net, [Demand("A", "B", load)])
            return next(u for u in result.utils
                        if u.link.link_id == "1")
        self.assertEqual(flag_for(7.9).flag, "OK")
        self.assertEqual(flag_for(8.0).flag, "HIGH")
        self.assertEqual(flag_for(10.0).flag, "HIGH")
        self.assertEqual(flag_for(10.1).flag, "OVER")
        self.assertEqual(flag_for(1).utilisation, 10.0)

    def test_unknown_node_demand_is_unroutable_not_error(self):
        result = apply_traffic(self.net, [Demand("A", "ZZZ", 1)])
        self.assertEqual(result.unroutable, 1)
        self.assertTrue(all(u.load == 0 for u in result.utils))

    def test_excluded_links_simulate_failure_set(self):
        result = apply_traffic(self.net, self.demands,
                               excluded=frozenset({"6"}))
        self.assertEqual(result.unroutable, 0)
        self.assertGreater(result.max_utilisation, 100)


class TestWCF(unittest.TestCase):
    def test_bridge_failure_ranks_worst(self):
        # Chain with no alternative route: removing either link
        # disconnects A->C, so the worst failure has 1 un-routable.
        chain = net_from("LinkId,Start,End,Capacity,Weight\n"
                         "1,A,B,10,1\n2,B,C,10,1\n")
        failures = worst_case_failures(chain, [Demand("A", "C", 2)])
        self.assertEqual(len(failures), 2)
        self.assertIn(failures[0].link_id, ("1", "2"))
        self.assertEqual(failures[0].unroutable, 1)

    def test_ranking_order_unroutable_then_over_then_max(self):
        # Build a network where one failure disconnects, another
        # overloads, and a third only raises max utilisation.
        net = net_from("LinkId,Start,End,Capacity,Weight\n"
                       "1,A,B,10,1\n2,B,C,10,1\n3,A,C,10,1\n")
        demands = [Demand("A", "B", 9), Demand("B", "C", 9)]
        failures = worst_case_failures(net, demands)
        # No failure disconnects here (triangle); just check the
        # list is sorted by the documented key.
        keys = [(-f.unroutable, -f.over_count, -f.max_utilisation)
                for f in failures]
        self.assertEqual(keys, sorted(keys))

    def test_page_wcf(self):
        net = net_from(PAGE_NETWORK)
        demands = traffic_from(PAGE_TRAFFIC)
        failures = worst_case_failures(net, demands)
        self.assertEqual(len(failures), 13)
        self.assertEqual(failures[0].link_id, "6")
        self.assertEqual(failures[0].over_count, 1)
        keys = [(-f.unroutable, -f.over_count, -f.max_utilisation)
                for f in failures]
        self.assertEqual(keys, sorted(keys))

    def test_wcf_does_not_mutate_network(self):
        net = net_from(PAGE_NETWORK)
        demands = traffic_from(PAGE_TRAFFIC)
        before = apply_traffic(net, demands)
        worst_case_failures(net, demands)
        after = apply_traffic(net, demands)
        self.assertEqual([u.load for u in before.utils],
                         [u.load for u in after.utils])


class TestReportsAndCLI(unittest.TestCase):
    def test_csv_writers(self):
        net = net_from(PAGE_NETWORK)
        result = apply_traffic(net, traffic_from(PAGE_TRAFFIC))
        with tempfile.TemporaryDirectory() as tmp:
            routes_path = Path(tmp) / "routes.csv"
            links_path = Path(tmp) / "links.csv"
            write_routes_csv(result, routes_path)
            write_links_csv(result, links_path)
            with open(routes_path, newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 5)
            self.assertEqual(rows[0]["Source"], "A")
            self.assertEqual(rows[0]["Routed"], "yes")
            with open(links_path, newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 13)
            self.assertEqual(rows[0]["LinkId"], "1")

    def test_svg_contains_nodes_and_red_over_link(self):
        net = net_from(PAGE_NETWORK)
        result = apply_traffic(net, [Demand("A", "B", 15)])
        svg = render_svg(net, result)
        self.assertTrue(svg.startswith("<svg"))
        self.assertEqual(svg.count("<circle"), 9)
        self.assertIn("#c0392b", svg)  # over-capacity link is red
        self.assertIn("Legend", svg)

    def test_svg_removed_link_is_dashed(self):
        net = net_from(PAGE_NETWORK)
        result = apply_traffic(net, traffic_from(PAGE_TRAFFIC),
                               excluded=frozenset({"6"}))
        svg = render_svg(net, result, excluded=frozenset({"6"}))
        self.assertIn("stroke-dasharray", svg)
        self.assertIn("(removed)", svg)

    def test_cli_commands(self):
        for cmd in ("routes", "report", "wcf"):
            proc = subprocess.run(
                [sys.executable, str(ROOT / "netmod.py"), cmd,
                 "--network", str(ROOT / "examples" / "network.csv"),
                 "--traffic", str(ROOT / "examples" / "traffic.csv")],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            if cmd == "wcf":
                self.assertIn("Worst case failure", proc.stdout)
            else:
                self.assertIn("A", proc.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.svg"
            proc = subprocess.run(
                [sys.executable, str(ROOT / "netmod.py"), "svg",
                 "--network", str(ROOT / "examples" / "network.csv"),
                 "--traffic", str(ROOT / "examples" / "traffic.csv"),
                 "--output", str(out)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(out.read_text().startswith("<svg"))

    def test_cli_bad_file_exits_nonzero(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "netmod.py"), "report",
             "--network", "/tmp/does-not-exist-netmod.csv",
             "--traffic", str(ROOT / "examples" / "traffic.csv")],
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("error", proc.stderr)


if __name__ == "__main__":
    unittest.main()
