def median(values):
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def range_of(values):
    if not values:
        raise ValueError("empty list")
    return max(values) - min(values)


def running_total(values):
    total = 0
    out = []
    for value in values:
        total += value
        out.append(total)
    return out
