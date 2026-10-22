def reachable(adj, start):
    seen = {start}
    for nb in adj.get(start, []):
        seen.add(nb)
    # TODO: continue exploring the neighbours' neighbours
    return seen
