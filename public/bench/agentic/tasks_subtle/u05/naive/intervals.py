def merge(intervals):
    intervals.sort()
    out = []
    for s, e in intervals:
        if not out or s >= out[-1][1]:
            out.append([s, e])
        else:
            out[-1][1] = max(out[-1][1], e)
    return out
