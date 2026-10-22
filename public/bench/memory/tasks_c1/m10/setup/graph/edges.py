def add_edge(adj, a, b):
    adj.setdefault(a, []).append(b)
    adj.setdefault(b, []).append(a)
    return adj

def neighbors(adj, node):
    return sorted(adj.get(node, []))
