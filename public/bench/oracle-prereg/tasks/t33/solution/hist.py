def histogram(values, edges):
    if len(edges) < 2:
        raise ValueError("edges must have at least 2 elements")
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            raise ValueError("edges must be strictly increasing")

    counts = [0] * (len(edges) - 1)
    e0 = edges[0]
    e_last = edges[-1]
    n_bins = len(edges) - 1

    for v in values:
        if v != v:
            continue
        if v < e0 or v > e_last:
            continue
        for i in range(n_bins):
            if i == n_bins - 1:
                if edges[i] <= v <= edges[i + 1]:
                    counts[i] += 1
                    break
            else:
                if edges[i] <= v < edges[i + 1]:
                    counts[i] += 1
                    break

    return counts

