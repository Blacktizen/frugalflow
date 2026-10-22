# Graph path finder — package `graph`

Six work items; each is one module inside `graph/`. Import modules with
`from graph import <module>`. Everything below is normative, including the edge
cases. Do not rename modules or functions.

Graphs are undirected adjacency dicts: `node -> list of neighbours` where every
edge is stored in both directions.

## Item 1 — `edges.py`
- `add_edge(adj, a, b)`: add the undirected edge `a-b` to `adj` in place
  (creating missing keys) and return `adj`.
- `neighbors(adj, node) -> list`: the sorted neighbours of `node`, or `[]` if
  the node is absent.

## Item 2 — `degree.py`
`degree(adj, node) -> int`
- The number of neighbours of `node` (0 if absent).

## Item 3 — `components.py`
`components(adj) -> list[set]`
- Return the connected components, each as a set of nodes, ordered by their
  smallest node. An isolated node is its own component.

## Item 4 — `reach.py`
`reachable(adj, start) -> set`
- Return the set of nodes reachable from `start` (including `start`), using
  depth-first traversal that tolerates cycles.

## Item 5 — `shortest.py`
`shortest(adj, start, goal) -> list | None`
- Return a shortest path (list of nodes) from `start` to `goal` using breadth
  first search, or `None` if unreachable. `start == goal` yields `[start]`.

## Item 6 — `count.py`
`edge_count(adj) -> int`
- Return the number of distinct undirected edges (each edge is stored twice).
