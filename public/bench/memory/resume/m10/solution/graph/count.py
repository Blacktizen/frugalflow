def edge_count(adj):
    total = 0
    for node, nbs in adj.items():
        total += len(nbs)
    return total // 2
