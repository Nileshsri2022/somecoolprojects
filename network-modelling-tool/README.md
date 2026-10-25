# Network Modelling Tool

Build Your Own Network Modelling Tool — Coding Challenges:
https://codingchallenges.fyi/challenges/challenge-network-modeller

A CLI tool (the page explicitly allows a command-line tool) that loads
an IP network and traffic demands from CSV, routes every demand along
its lowest-total-weight (OSPF-style shortest) path using Dijkstra's
algorithm, reports per-demand routes and per-link utilisation, ranks
single-link Worst Case Failures, and renders a static SVG map.
Python 3 standard library only — no packages to install.

## Quick start

```bash
# Routes + link utilisation for the page's example network/traffic
python3 netmod.py report --network examples/network.csv \
    --traffic examples/traffic.csv

# Per-demand routes only
python3 netmod.py routes --network examples/network.csv \
    --traffic examples/traffic.csv

# Worst Case Failure: every single-link failure, worst first
python3 netmod.py wcf --network examples/network.csv \
    --traffic examples/traffic.csv

# Static SVG map (green < 80%, amber 80–100%, red > 100%)
python3 netmod.py svg --network examples/network.csv \
    --traffic examples/traffic.csv --output network.svg

# Simulate a specific failure set (report / svg only)
python3 netmod.py report --network examples/network.csv \
    --traffic examples/traffic.csv --remove 6,13

# Write CSV reports
python3 netmod.py report --network examples/network.csv \
    --traffic examples/traffic.csv \
    --routes-out routes.csv --links-out links.csv
```

## Input formats

Network CSV — `LinkId,Start,End,Capacity,Weight`. Every link is
bi-directional with symmetrical capacity. Traffic CSV —
`Source,Destination,Demand`. Headers are matched case-insensitively;
see `examples/` for the page's own 13-link network and 5 demands.

## Example output (baseline, page example)

Link 6 (G–H) carries 10/10 = 100% (HIGH); all other links are below
80%. The worst single-link failure is removing link 6, which pushes
one link to 120% (OVER). Full details: `docs/SPEC.md`.

## Tests

```bash
python3 -m unittest discover -s tests -v   # 31 tests, all passing
```

## Scope limits (honest)

- CLI + static SVG only — no GUI editor, no editable node positions,
  no latitude/longitude map rendering.
- No real network devices or live traffic; all input is CSV.
- WCF ranks single-link failures only; a specific multi-link failure
  set can be simulated with `--remove`, but exhaustive multi-link
  WCF is not built.
- One shortest path per demand — no ECMP splitting, no
  capacity-aware re-routing, no weight optimisation.
- See `docs/SPEC.md` for every divergence from the challenge page
  and `docs/DESIGN.md` / `docs/TEST_PLAN.md` for design and coverage.
