def merge_intervals(items):
    if not items:
        return []
    items.sort()
    merged = [tuple(items[0])]
    for start, end in items[1:]:
        if start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged

