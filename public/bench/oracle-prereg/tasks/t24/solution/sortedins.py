import bisect

def insert_sorted(xs, x, key=None):
    if key is None:
        pos = bisect.bisect_right(xs, x)
    else:
        keys = [key(e) for e in xs]
        pos = bisect.bisect_right(keys, key(x))
    result = list(xs)
    result.insert(pos, x)
    return result

