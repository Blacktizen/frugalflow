from plan import compress

def total(intervals):
    return sum(e - s for s, e in compress.merge(intervals))
