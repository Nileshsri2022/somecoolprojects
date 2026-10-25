# SPEC — Network Modelling Tool

Source challenge: https://codingchallenges.fyi/challenges/challenge-network-modeller
("Build Your Own Network Modelling Tool", Coding Challenges, read 2026-10-25.)
This is a CLI modelling tool, as the page explicitly allows
("You can build this as a command line tool that outputs another CSV").

## What the tool does

Load a network from CSV, load traffic demands from CSV, route every
demand along its shortest (lowest total link-weight) path, report the
route of each demand and the load/utilisation of every link, and
compute the Worst Case Failure (WCF): the single-link failure whose
removal hurts the network most.

## Challenge steps, as implemented

### Step 0 — Language / setup
Python 3, standard library only. No third-party packages, no build
step: run `python3 netmod.py <command> ...`.

### Step 1 — Load a network from CSV
Input columns (header row required, matching is case-insensitive and
surrounding whitespace is ignored):

```
LinkId,Start,End,Capacity,Weight
```

Example from the page (13 links, nodes A–I, every link capacity 10):

| LinkId | Start | End | Capacity | Weight |
| --- | --- | --- | --- | --- |
| 1 | A | B | 10 | 5 |
| 2 | B | C | 10 | 5 |
| 3 | C | D | 10 | 5 |
| 4 | D | E | 10 | 5 |
| 5 | E | F | 10 | 5 |
| 6 | G | H | 10 | 5 |
| 7 | H | A | 10 | 5 |
| 8 | A | I | 10 | 5 |
| 9 | B | I | 10 | 1 |
| 10 | C | G | 10 | 5 |
| 11 | D | F | 10 | 1 |
| 12 | I | G | 10 | 5 |
| 13 | F | G | 10 | 3 |

Rules, exactly as the page states:
- Every link is **bi-directional with symmetrical capacity**: traffic
  in either direction loads the same link.
- Links are modelled as a graph: nodes are the distinct Start/End
  values, links carry an id, two endpoints, a capacity and a weight.

Validation (errors abort with a clear message, exit code non-zero):
- Missing/renamed columns, empty file, or a non-numeric
  Capacity/Weight/LinkId are errors.
- Capacity must be > 0; Weight must be >= 0 (Dijkstra requires
  non-negative weights — see Divergences).
- Duplicate LinkId is an error.
- A self-loop (Start == End) is an error.
- Parallel links between the same pair of nodes are allowed; they are
  distinct links and routing picks the lowest-weight one (ties broken
  deterministically, see DESIGN.md).

The page mentions adding x/y coordinates "if you're building a GUI".
This build is CLI-only, so no coordinates are read or required; the
SVG visualisation lays nodes out deterministically on a circle
(see Divergences).

### Step 2 — Paths through the network (OSPF-style shortest path)
Traffic from a source to a destination follows the path with the
**lowest total link weight** (the page's OSPF model). The page
suggests Dijkstra's algorithm (or BFS/DFS/Bellman–Ford); this build
uses Dijkstra's algorithm.

- Tie-breaking is deterministic: among equal-weight paths, the
  lexicographically smallest node sequence wins. This makes output
  reproducible run to run.
- A demand whose endpoints are disconnected (or unknown) after any
  link removals is **un-routable**: it contributes no link load and is
  listed as such in reports.
- A demand with Source == Destination is routed with an empty path
  (zero hops, no link load). It is not counted as un-routable.

### Step 3 — Load traffic data from CSV
Input columns (header row required, case-insensitive):

```
Source,Destination,Demand
```

Example from the page:

| Source | Destination | Demand |
| --- | --- | --- |
| A | E | 1 |
| B | A | 3 |
| I | E | 2 |
| A | G | 5 |
| H | D | 4 |

Validation: Demand must be > 0; missing columns or non-numeric
demands are errors. Demands naming nodes absent from the network are
**not** rejected at load time; they surface as un-routable demands
when routed, so a traffic file can be checked against any network.

### Step 4 — Apply traffic, report link utilisation
For each demand, route it along the shortest path and add its Demand
to the load of every link on that path (in both directions the load
is the same link's load — links are bidirectional).

Outputs:
- Per-demand route report: source, destination, demand, node path,
  link ids used, total weight, and routed/un-routable status.
- Per-link report: link id, endpoints, capacity, total load,
  utilisation percent (`load / capacity * 100`), and a flag.
  A link **can exceed 100%** — that is reported, not capped.
- Flags follow the page's thresholds: `OK` below 80%,
  `HIGH` at >= 80% and <= 100%, `OVER` above 100%.
- CLI commands print these as tables; `--routes-out` / `--links-out`
  write them as CSV files (the page's "outputs another CSV" option).

### Step 5 — Worst Case Failure (WCF)
For each single link in turn: remove that link, re-route all demands,
and score the resulting network. Ranking, per the page, worst first:

1. Highest number of un-routable traffic demands.
2. Then highest number of links over capacity (> 100% utilisation).
3. Then highest maximum link utilisation (the network "closest to
   reaching capacity" when nothing is over capacity).

The WCF report lists every single-link failure in worst-first order
plus the single worst case, and the baseline (no failure) for
comparison. Removing a link never changes the other links' capacities
or weights.

## Going Further (page suggestions) — status
- Refine visualisation / move nodes around / latitude-longitude map
  rendering: **NOT built**. The SVG output uses a fixed deterministic
  circle layout; node positions cannot be edited and no map is drawn.
- Extend WCF to multiple link failures: **NOT built as an exhaustive
  search**. A specific failure set *can* be simulated with
  `--remove <id,...>` on the `report` / `svg` commands (e.g. remove
  links 9 and 11 together and see the result), but the `wcf` command
  itself only ranks single-link failures. This is an honest scope
  limit, not a silent omission.
- GUI editor / desktop or web GUI: **NOT built** (CLI + static SVG
  only, per the page's explicit CLI option).
- Real network devices, live traffic, SNMP/OSPF daemons: **NOT built
  and never claimed**. All input is CSV; all routing is offline
  modelling.

## Deliberate divergences from the page
1. **Negative weights rejected.** The page never says weights can be
   negative; Dijkstra's algorithm (the page's recommended approach)
   is only correct for non-negative weights. Negative weights are
   therefore a load error, rather than silently producing wrong
   paths. Zero weight is allowed.
2. **Deterministic tie-breaking.** The page does not specify what
   happens when two paths have equal total weight. This build picks
   the lexicographically smallest node sequence, so identical inputs
   always give identical output.
3. **SVG layout without coordinates.** The page's x/y coordinates are
   a GUI suggestion. The static SVG places nodes on a circle in
   sorted-node order — deterministic, but not a geographic layout
   and not editable.
4. **Unknown traffic nodes are un-routable, not load errors.** This
   keeps the tool usable for checking a traffic file against a
   network, and matches the page's own "un-routable traffic demands"
   concept in Step 5.
5. **Demand units are abstract.** The page gives no units for
   Capacity or Demand; both are treated as the same abstract unit
   and utilisation is their ratio, so no unit conversion is claimed.

## Non-goals
No GUI, no map, no live network access, no multi-link exhaustive
WCF, no traffic engineering beyond shortest-path routing (no ECMP
splitting, no capacity-aware re-routing, no weight optimisation).
A demand is never split across parallel paths: it takes one shortest
path in full, as the page's Step 4 describes.
