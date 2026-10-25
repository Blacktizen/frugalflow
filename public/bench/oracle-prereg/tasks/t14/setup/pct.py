def pct_change(old, new):
    if old == 0:
        return None
    result = (new - old) / old * 100
    return round(result, 2)

