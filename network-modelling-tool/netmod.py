#!/usr/bin/env python3
"""Network modelling tool (Coding Challenges: challenge-network-modeller).

Load a network and traffic demands from CSV, route each demand along
its lowest-total-weight (OSPF-style shortest) path with Dijkstra's
algorithm, report per-demand routes and per-link utilisation, rank
single-link Worst Case Failures, and render a static SVG map.

Python 3 standard library only. No GUI, no live network access.
Usage: python3 netmod.py {routes|report|wcf|svg} --network N.csv
       --traffic T.csv [--remove 3,5] [--routes-out R.csv]
       [--links-out L.csv] [--output out.svg]
"""

import argparse
import csv
import heapq
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path


class NetmodError(ValueError):
    """User-facing load/validation error."""


# ---------------------------------------------------------------- data model

@dataclass(frozen=True)
class Link:
    link_id: str
    start: str
    end: str
    capacity: float
    weight: float


@dataclass(frozen=True)
class Demand:
    source: str
    destination: str
    demand: float


@dataclass
class Network:
    links: list
    nodes: set = field(default_factory=set)

    def __post_init__(self):
        nodes = set()
        for link in self.links:
            nodes.add(link.start)
            nodes.add(link.end)
        self.nodes = nodes

    def adjacency(self, excluded=frozenset()):
        """node -> [(neighbour, weight, link_id)] for non-excluded links."""
        adj = {node: [] for node in self.nodes}
        for link in self.links:
            if link.link_id in excluded:
                continue
            adj[link.start].append((link.end, link.weight, link.link_id))
            adj[link.end].append((link.start, link.weight, link.link_id))
        return adj


@dataclass
class Route:
    demand: Demand
    nodes: tuple = ()
    link_ids: tuple = ()
    total_weight: float | None = None
    routed: bool = False


@dataclass
class LinkUtil:
    link: Link
    load: float = 0.0

    @property
    def utilisation(self):
        return self.load / self.link.capacity * 100.0

    @property
    def flag(self):
        if self.utilisation > 100:
            return "OVER"
        if self.utilisation >= 80:
            return "HIGH"
        return "OK"


@dataclass
class TrafficResult:
    routes: list
    utils: list  # LinkUtil, one per link, in file order

    @property
    def unroutable(self):
        return sum(1 for r in self.routes if not r.routed)

    @property
    def over_count(self):
        return sum(1 for u in self.utils if u.utilisation > 100)

    @property
    def max_utilisation(self):
        return max((u.utilisation for u in self.utils), default=0.0)


@dataclass
class FailureResult:
    link_id: str
    result: TrafficResult

    @property
    def unroutable(self):
        return self.result.unroutable

    @property
    def over_count(self):
        return self.result.over_count

    @property
    def max_utilisation(self):
        return self.result.max_utilisation


# ---------------------------------------------------------------- CSV loading

def _normalised_header(fieldnames):
    """Map lower-cased stripped header -> original header."""
    if not fieldnames:
        raise NetmodError("CSV file is empty (no header row)")
    mapping = {}
    for name in fieldnames:
        if name is None:
            continue
        mapping[name.strip().lower()] = name
    return mapping


def _read_rows(path, required):
    try:
        handle = open(path, newline="", encoding="utf-8")
    except OSError as exc:
        raise NetmodError(f"cannot open {path}: {exc}") from exc
    with handle:
        reader = csv.DictReader(handle)
        mapping = _normalised_header(reader.fieldnames)
        missing = [c for c in required if c not in mapping]
        if missing:
            raise NetmodError(
                f"{path}: missing required column(s): {', '.join(missing)}")
        rows = []
        for lineno, raw in enumerate(reader, start=2):
            if raw is None:
                continue
            # Skip fully blank lines.
            values = {k: (v.strip() if isinstance(v, str) else v)
                      for k, v in raw.items() if k is not None}
            if all(v in (None, "") for v in values.values()):
                continue
            row = {}
            for col in required:
                row[col] = values.get(mapping[col])
            rows.append((lineno, row))
    if not rows:
        raise NetmodError(f"{path}: no data rows")
    return rows


def _parse_number(path, lineno, column, value):
    if value is None or value == "":
        raise NetmodError(f"{path} line {lineno}: empty {column}")
    try:
        number = float(value)
    except ValueError as exc:
        raise NetmodError(
            f"{path} line {lineno}: {column} {value!r} is not a number"
        ) from exc
    if not math.isfinite(number):
        raise NetmodError(f"{path} line {lineno}: {column} must be finite")
    return number


def load_network(path):
    links = []
    seen_ids = set()
    for lineno, row in _read_rows(
            path, ["linkid", "start", "end", "capacity", "weight"]):
        link_id = row["linkid"]
        start, end = row["start"], row["end"]
        if not link_id or not start or not end:
            raise NetmodError(
                f"{path} line {lineno}: LinkId, Start and End are required")
        if link_id in seen_ids:
            raise NetmodError(
                f"{path} line {lineno}: duplicate LinkId {link_id!r}")
        seen_ids.add(link_id)
        if start == end:
            raise NetmodError(
                f"{path} line {lineno}: self-loop on node {start!r}")
        capacity = _parse_number(path, lineno, "Capacity", row["capacity"])
        weight = _parse_number(path, lineno, "Weight", row["weight"])
        if capacity <= 0:
            raise NetmodError(
                f"{path} line {lineno}: Capacity must be > 0")
        if weight < 0:
            raise NetmodError(
                f"{path} line {lineno}: Weight must be >= 0 "
                "(Dijkstra requires non-negative weights)")
        links.append(Link(link_id, start, end, capacity, weight))
    return Network(links)


def load_traffic(path):
    demands = []
    for lineno, row in _read_rows(path, ["source", "destination", "demand"]):
        source, dest = row["source"], row["destination"]
        if not source or not dest:
            raise NetmodError(
                f"{path} line {lineno}: Source and Destination are required")
        demand = _parse_number(path, lineno, "Demand", row["demand"])
        if demand <= 0:
            raise NetmodError(
                f"{path} line {lineno}: Demand must be > 0")
        demands.append(Demand(source, dest, demand))
    return demands


# ---------------------------------------------------------------- routing

def shortest_path(network, source, destination, excluded=frozenset()):
    """Lowest-weight path, or None. Ties: lexicographically smallest nodes.

    Dijkstra over links: the queue key (weight, node-tuple, node,
    link-tuple) makes the first pop of the destination deterministic.
    """
    if source not in network.nodes or destination not in network.nodes:
        return None
    if source == destination:
        return Route(Demand(source, destination, 0), (), (), 0.0, True)
    adj = network.adjacency(excluded)
    best = {source: (0.0, ())}
    queue = [(0.0, (source,), source, ())]
    visited = set()
    while queue:
        cost, node_path, node, link_path = heapq.heappop(queue)
        if node in visited:
            continue
        visited.add(node)
        if node == destination:
            return Route(Demand(source, destination, 0), node_path,
                         link_path, cost, True)
        for neighbour, weight, link_id in adj[node]:
            new_cost = cost + weight
            new_path = node_path + (neighbour,)
            if (neighbour not in best
                    or (new_cost, new_path) < best[neighbour]):
                best[neighbour] = (new_cost, new_path)
                heapq.heappush(queue, (new_cost, new_path, neighbour,
                                      link_path + (link_id,)))
    return None


def apply_traffic(network, demands, excluded=frozenset()):
    loads = {link.link_id: 0.0 for link in network.links}
    routes = []
    for demand in demands:
        found = shortest_path(network, demand.source, demand.destination,
                              excluded)
        if found is None:
            routes.append(Route(demand, (), (), None, False))
        else:
            routes.append(Route(demand, found.nodes, found.link_ids,
                                found.total_weight, True))
            for link_id in found.link_ids:
                loads[link_id] += demand.demand
    utils = [LinkUtil(link, loads[link.link_id]) for link in network.links]
    return TrafficResult(routes, utils)


def _link_sort_key(link_id):
    try:
        return (0, float(link_id))
    except (TypeError, ValueError):
        return (1, str(link_id))


def worst_case_failures(network, demands):
    """One FailureResult per link, worst first (page Step 5 ranking)."""
    results = []
    for link in network.links:
        result = apply_traffic(network, demands, frozenset({link.link_id}))
        results.append(FailureResult(link.link_id, result))
    results.sort(key=lambda f: (-f.unroutable, -f.over_count,
                                -f.max_utilisation,
                                _link_sort_key(f.link_id)))
    return results


# ---------------------------------------------------------------- reports

def _fmt(number):
    if number is None:
        return "-"
    if float(number) == int(number):
        return str(int(number))
    return f"{number:g}"


def format_routes(result):
    lines = ["Source Dest Demand Path Links Weight Routed"]
    for route in result.routes:
        d = route.demand
        lines.append(
            f"{d.source:<6} {d.destination:<4} {_fmt(d.demand):<6} "
            f"{'->'.join(route.nodes) if route.nodes else '-':<20} "
            f"{','.join(route.link_ids) if route.link_ids else '-':<12} "
            f"{_fmt(route.total_weight):<6} "
            f"{'yes' if route.routed else 'NO'}")
    return "\n".join(lines)


def format_links(result):
    lines = ["Link Start End Capacity Load Util% Flag  Bar"]
    for util in result.utils:
        bar = "#" * min(40, int(util.utilisation // 5)) if util.utilisation > 0 else ""
        lines.append(
            f"{util.link.link_id:<4} {util.link.start:<5} {util.link.end:<3} "
            f"{_fmt(util.link.capacity):<8} {_fmt(util.load):<5} "
            f"{util.utilisation:>5.1f}% {util.flag:<4} {bar}")
    return "\n".join(lines)


def write_routes_csv(result, path):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Source", "Destination", "Demand", "Path", "Links",
                         "TotalWeight", "Routed"])
        for route in result.routes:
            writer.writerow([
                route.demand.source, route.demand.destination,
                _fmt(route.demand.demand),
                "->".join(route.nodes), ",".join(route.link_ids),
                _fmt(route.total_weight),
                "yes" if route.routed else "no"])


def write_links_csv(result, path):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["LinkId", "Start", "End", "Capacity", "Load",
                         "UtilisationPct", "Flag"])
        for util in result.utils:
            writer.writerow([
                util.link.link_id, util.link.start, util.link.end,
                _fmt(util.link.capacity), _fmt(util.load),
                f"{util.utilisation:.1f}", util.flag])


# ---------------------------------------------------------------- SVG

def render_svg(network, result, excluded=frozenset()):
    """Static SVG: nodes on a circle, links coloured by utilisation."""
    nodes = sorted(network.nodes)
    width, height = 640, 520
    cx, cy, radius = 320, 260, 200
    import math as _math
    pos = {}
    for i, node in enumerate(nodes):
        angle = 2 * _math.pi * i / max(1, len(nodes)) - _math.pi / 2
        pos[node] = (cx + radius * _math.cos(angle),
                     cy + radius * _math.sin(angle))
    util_by_id = {u.link.link_id: u for u in result.utils}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="16" y="24" font-family="sans-serif" font-size="16">'
        'Network model</text>',
    ]
    for link in network.links:
        x1, y1 = pos[link.start]
        x2, y2 = pos[link.end]
        if link.link_id in excluded:
            colour, dash = "#999999", ' stroke-dasharray="6,4"'
            label = f"{link.link_id} (removed)"
        else:
            util = util_by_id[link.link_id]
            colour = ("#c0392b" if util.utilisation > 100 else
                      "#d4850a" if util.utilisation >= 80 else "#2e7d32")
            dash = ""
            label = f"{link.link_id} {util.utilisation:.0f}%"
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        parts.append(
            f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
            f'stroke="{colour}" stroke-width="2"{dash}/>')
        parts.append(
            f'<text x="{mx:.0f}" y="{my:.0f}" font-family="sans-serif" '
            f'font-size="11" text-anchor="middle">{label}</text>')
    for node, (x, y) in pos.items():
        parts.append(
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="18" fill="#dce8f5" '
            f'stroke="#335577"/>')
        parts.append(
            f'<text x="{x:.0f}" y="{y:.0f}" font-family="sans-serif" '
            f'font-size="13" text-anchor="middle" '
            f'dominant-baseline="middle">{node}</text>')
    parts.append(
        '<text x="16" y="500" font-family="sans-serif" font-size="12">'
        'Legend: green &lt; 80%  amber 80-100%  red &gt; 100%  '
        'grey dashed = removed</text>')
    parts.append('</svg>')
    return "\n".join(parts)


# ---------------------------------------------------------------- CLI

def _parse_remove(value):
    if not value:
        return frozenset()
    ids = [part.strip() for part in value.split(",") if part.strip()]
    if not ids:
        raise NetmodError("--remove must list at least one link id")
    return frozenset(ids)


def _load(args):
    network = load_network(args.network)
    demands = load_traffic(args.traffic)
    excluded = (_parse_remove(args.remove)
                if getattr(args, "remove", "") else frozenset())
    unknown = [link_id for link_id in excluded
               if link_id not in {l.link_id for l in network.links}]
    if unknown:
        raise NetmodError(
            f"--remove names unknown link id(s): {', '.join(sorted(unknown))}")
    return network, demands, excluded


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="netmod",
        description="Model IP-network traffic and worst-case link failures.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("routes", "report", "wcf", "svg"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--network", required=True)
        cmd.add_argument("--traffic", required=True)
        if name in ("routes", "report", "svg"):
            cmd.add_argument("--remove", default="")
        if name == "report":
            cmd.add_argument("--routes-out", default="")
            cmd.add_argument("--links-out", default="")
        if name == "svg":
            cmd.add_argument("--output", default="")
    args = parser.parse_args(argv)
    try:
        network, demands, excluded = _load(args)
        if args.command in ("routes", "report"):
            result = apply_traffic(network, demands, excluded)
            print(format_routes(result))
            if args.command == "report":
                print()
                print(format_links(result))
                print(f"\nUn-routable demands: {result.unroutable}  "
                      f"Links over capacity: {result.over_count}  "
                      f"Max utilisation: {result.max_utilisation:.1f}%")
                if args.routes_out:
                    write_routes_csv(result, args.routes_out)
                if args.links_out:
                    write_links_csv(result, args.links_out)
        elif args.command == "wcf":
            baseline = apply_traffic(network, demands)
            failures = worst_case_failures(network, demands)
            print(f"Baseline: un-routable={baseline.unroutable} "
                  f"over={baseline.over_count} "
                  f"max={baseline.max_utilisation:.1f}%")
            print("Worst case first:")
            for failure in failures:
                print(f"  remove link {failure.link_id}: "
                      f"un-routable={failure.unroutable} "
                      f"over={failure.over_count} "
                      f"max={failure.max_utilisation:.1f}%")
            worst = failures[0]
            print(f"Worst case failure: link {worst.link_id} "
                  f"(un-routable={worst.unroutable}, "
                  f"over={worst.over_count}, "
                  f"max={worst.max_utilisation:.1f}%)")
        elif args.command == "svg":
            result = apply_traffic(network, demands, excluded)
            svg = render_svg(network, result, excluded)
            if args.output:
                Path(args.output).write_text(svg, encoding="utf-8")
                print(f"Wrote {args.output}")
            else:
                print(svg)
    except NetmodError as exc:
        print(f"netmod: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
