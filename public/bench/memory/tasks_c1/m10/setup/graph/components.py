def components(adj):
    seen = set()
    result = []
    for node in sorted(adj):
        if node in seen:
            continue
        comp = set()
        stack = [node]
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp.add(cur)
            for nb in adj.get(cur, []):
                if nb not in comp:
                    stack.append(nb)
        seen |= comp
        result.append(comp)
    return result
