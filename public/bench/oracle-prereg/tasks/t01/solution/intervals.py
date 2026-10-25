def merge_intervals(items):
    if not items:
        return []
    for start, end in items:
        if start > end:
            raise ValueError("start must be <= end")
    sorted_items = sorted((start, end) for start, end in items)
    merged = [tuple(sorted_items[0])]
    for start, end in sorted_items[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged

