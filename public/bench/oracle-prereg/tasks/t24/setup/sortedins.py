import bisect

def insert_sorted(xs, x, key=None):
    if key is None:
        pos = bisect.bisect_left(xs, x)
    else:
        keys = [key(e) for e in xs]
        pos = bisect.bisect_left(keys, key(x))
    xs.insert(pos, x)
    return xs

