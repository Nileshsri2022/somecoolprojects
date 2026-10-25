# DESIGN — Network Modelling Tool

## Files
- `netmod.py` — the whole tool (single file, Python 3 stdlib only):
  CSV loading, graph model, Dijkstra routing, traffic application,
  WCF ranking, text/CSV reports, static SVG visualisation, CLI.
- `examples/network.csv` — the page's 13-link example network.
- `examples/traffic.csv` — the page's 5-demand example traffic.
- `tests/test_netmod.py` — unittest suite (see TEST_PLAN.md).

## Data model
- `Link`: dataclass (`link_id: str`, `start`, `end`, `capacity: float`,
  `weight: float`). Link ids are kept as strings as written in the
  CSV (so `01` stays `01`); sorting of link ids for display is by
  numeric value when possible, else lexicographically.
- `Network`: `links` (list, in file order), `nodes` (sorted set of
  endpoint names), and an adjacency index built on demand:
  `node -> [(neighbour, weight, link_id), ...]`, with one entry per
  direction per link. Parallel links appear as separate entries.
- `Demand`: dataclass (`source`, `destination`, `demand: float`).
- `Route`: dataclass (`demand`, `nodes` tuple, `link_ids` tuple,
  `total_weight: float | None`, `routed: bool`). `routed=False`
  means no path exists (or an endpoint is unknown); `nodes` is then
  empty and `total_weight` is None. A same-node demand is routed
  with empty nodes/links and weight 0.

## Routing: Dijkstra with deterministic ties
`shortest_path(network, source, destination, excluded=frozenset())`
runs Dijkstra over links (not just nodes), so parallel links are
handled correctly: the priority queue holds
`(total_weight, node_path_tuple, node, link_path_tuple)`. Because
the path tuple is the second queue key, equal-weight paths pop in
lexicographic node order — the first time the destination is popped,
its path is the lowest-weight, lexicographically smallest one.
`excluded` is a set of link ids removed for failure simulation; it
is a filter on adjacency entries, so the base network is never
mutated by a simulation.

Complexity is O((V + E) log V) per demand; WCF is O(L) routings of
all demands, which is fine for modelling-scale CSVs and is the
straightforward reading of the page's Step 5.

## Traffic application
`apply_traffic(network, demands, excluded)` routes each demand once
and accumulates `load[link_id] += demand` for each link on its path.
Link utilisation is `load / capacity * 100`, computed in
`link_utilisations(...)`, which returns one row per link (including
zero-load links) plus the `OK` / `HIGH` (>= 80%) / `OVER` (> 100%)
flag. Utilisation is never capped at 100%.

## Worst Case Failure
`worst_case_failures(network, demands)` returns one `FailureResult`
per link (baseline is computed separately by `apply_traffic` with no
exclusions) containing: removed link id, un-routable count,
over-capacity link count, maximum utilisation, and the full routing
result for that scenario. Sorting key, worst first:
`(-unroutable, -over_capacity_count, -max_utilisation, link_sort_key)`.
The final link-sort key only breaks exact ties deterministically; it
never overrides the three page-specified criteria.

## CLI
```
python3 netmod.py routes  --network N.csv --traffic T.csv [--remove 3,5]
python3 netmod.py report  --network N.csv --traffic T.csv [--remove 3,5]
                           [--routes-out routes.csv] [--links-out links.csv]
python3 netmod.py wcf     --network N.csv --traffic T.csv
python3 netmod.py svg     --network N.csv --traffic T.csv [--remove 3,5]
                           [--output out.svg]
```
- `routes`: per-demand routes only.
- `report`: per-demand routes + per-link utilisation table, with
  ASCII bars (one `#` per 5% utilisation, capped at 40 chars so an
  over-capacity link does not flood the terminal).
- `wcf`: baseline summary + every single-link failure, worst first,
  and the single worst link highlighted.
- `svg`: static SVG. Nodes on a circle (sorted order, equal angles),
  links as lines coloured by utilisation — green < 80%, amber
  80–100%, red > 100% — with link id + utilisation% labels and a
  legend. Removed links are drawn dashed grey and carry no load.
  No JavaScript, no interactivity, no external assets.
- All commands exit non-zero with a message on stderr for load
  errors, missing files, or malformed `--remove` values. A network
  with un-routable demands is *not* an error: it is reported.

## CSV parsing rules
- Header matching is case-insensitive with whitespace stripped, so
  `LinkId`, `linkid` and ` LinkId ` all work; extra columns are
  ignored; missing required columns are errors.
- Blank lines are skipped. A row with a missing/empty required field
  is an error naming the line number.
- Numbers parse with `float()` (LinkId stays a string). `nan`/`inf`
  values are rejected as non-finite.

## What is deliberately simple
- One shortest path per demand, no ECMP splitting, no load balancing.
- No persistence beyond CSV in / SVG out; no config file.
- No threads, no servers, no network access at runtime.
