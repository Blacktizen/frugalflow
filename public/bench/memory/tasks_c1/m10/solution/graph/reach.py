def reachable(adj, start):
    seen = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        for nb in adj.get(node, []):
            if nb not in seen:
                stack.append(nb)
    return seen
