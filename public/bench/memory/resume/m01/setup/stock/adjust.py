def apply(totals, name, delta):
    if not isinstance(delta, int):
        raise ValueError("delta must be an integer")
    current = totals.get(name, 0)
    # TODO: reject adjustments that would make the quantity negative
    totals[name] = current + delta
    return totals
