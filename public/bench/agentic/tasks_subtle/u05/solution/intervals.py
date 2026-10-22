def merge(intervals):
    if not intervals:
        return []
    ivs = [(min(s, e), max(s, e)) for s, e in intervals]
    ivs.sort()
    out = [list(ivs[0])]
    for s, e in ivs[1:]:
        if s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1][1] = e
        else:
            out.append([s, e])
    return out
