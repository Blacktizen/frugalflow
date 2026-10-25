def histogram(values, edges):
    if len(edges) < 2:
        raise ValueError("edges must have at least 2 elements")
    for i in range(1, len(edges)):
        if edges[i] < edges[i - 1]:
            raise ValueError("edges must be increasing")

    counts = [0] * (len(edges) - 1)

    for v in values:
        if v < edges[0] or v > edges[-1]:
            continue
        for i in range(len(edges) - 1):
            if edges[i] <= v < edges[i + 1]:
                counts[i] += 1
                break

    return counts

