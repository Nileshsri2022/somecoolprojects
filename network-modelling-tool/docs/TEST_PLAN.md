# TEST_PLAN — Network Modelling Tool

Run from the project directory:

```
python3 -m unittest discover -s tests -v
```

No third-party packages, no servers, no network access. All tests
are headless and deterministic.

## Coverage map

### Loading (Step 1 / Step 3)
- Page example network loads: 9 nodes (A–I), 13 links, link 9 is
  B–I capacity 10 weight 1, link 11 is D–F capacity 10 weight 1.
- Page example traffic loads: 5 demands, in file order.
- Case-insensitive / whitespace-padded headers accepted; extra
  columns ignored.
- Errors: missing column, empty file, non-numeric capacity,
  zero/negative capacity, negative weight, duplicate LinkId,
  self-loop, non-positive demand, non-numeric demand.
- Links are bidirectional: a path can traverse a link in either
  direction (e.g. H->A uses link 7 defined as H/A, A->H too).

### Routing (Step 2)
- Direct link, two-hop chain, and the page example:
  - A->D shortest path is A-H-G-F-D (weight 14), *not* A-B-C-D
    (15) or A-I-B-C-D (16), because weights, not hop count, decide
    — the weight-1 D-F link in reverse makes the H route win.
  - B->A uses the direct link 1 A-B (weight 5), beating B-I-A (6).
  - D->F is the direct link 11 (weight 1), not D-C-G-F (13).
- Tie-breaking: on a diamond with two equal-weight paths, the
  lexicographically smallest node sequence is returned, and repeated
  runs agree.
- Parallel links: the lowest-weight parallel link is chosen.
- Zero-weight link allowed and preferred.
- Unreachable destination and unknown node -> un-routable, no crash.
- Same-node demand -> routed, empty path, weight 0.
- Excluding a link re-routes around it; excluding every link on all
  paths makes the demand un-routable.

### Traffic application (Step 4)
- Single demand loads exactly its path links, nothing else.
- Bidirectional loading: A->B and B->A demands both load the same
  link (loads add, they do not cancel).
- Page example traffic: total routed demands and per-link loads are
  asserted against hand-computed values from the shortest paths
  (see the test comments for the path-by-path derivation).
- Over-capacity: a demand larger than a link's capacity reports
  utilisation > 100% with flag OVER, uncapped.
- Threshold flags: < 80% OK, exactly 80% HIGH, 100% HIGH, > 100% OVER.
- Utilisation of an unused link is 0% / OK.

### Worst Case Failure (Step 5)
- On a small triangle-ish network, removing the bridge link creates
  un-routable demands and ranks worst; removing a redundant link
  ranks better.
- Ranking order follows the page: un-routable count dominates
  over-capacity count, which dominates max utilisation.
- WCF over the page example network returns one result per link
  (13), the worst result is a real link, and the baseline has
  zero un-routable demands.
- Removing a link never mutates the base network (re-running the
  baseline after a WCF run gives identical loads).

### CLI / reports / SVG
- `routes`, `report`, `wcf`, `svg` CLI entry points run via
  subprocess on the example files and exit 0; their stdout/file
  output contains the expected node names, link ids and flags.
- `svg` output is a well-formed-enough SVG: starts with `<svg`,
  contains one `<circle` per node and the legend text, and colours
  an over-capacity link red.
- CSV report writers produce headers
  `Source,Destination,Demand,Path,Links,TotalWeight,Routed` and
  `LinkId,Start,End,Capacity,Load,UtilisationPct,Flag`, with one row
  per demand / link.
- Load errors via CLI exit non-zero.

## Hand-computed page-example expectations
Where a path is hand-asserted (A->D, B->A, D->F above), the weight
arithmetic is shown in the test comment. To avoid brittle hand
arithmetic on the full 9-node graph, the full-traffic test
cross-checks per-link loads against an independent brute-force
shortest-path implementation in the test file, and separately
asserts load conservation: the sum of all link loads equals the sum
over routed demands of (demand x path length in links).
