def apply(totals, name, delta):
    if not isinstance(delta, int):
        raise ValueError("delta must be an integer")
    current = totals.get(name, 0)
    if current + delta < 0:
        raise ValueError("quantity cannot become negative")
    totals[name] = current + delta
    return totals
