def merge(intervals):
    if not intervals:
        return []
    ordered = sorted(intervals)
    result = [list(ordered[0])]
    for s, e in ordered[1:]:
        last = result[-1]
        if s <= last[1]:
            last[1] = max(last[1], e)
        else:
            result.append([s, e])
    return [(s, e) for s, e in result]
