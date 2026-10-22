HOURS = {"s": 1 / 3600, "min": 1 / 60, "h": 1.0}

def to_hours(value, unit):
    if unit not in HOURS:
        raise ValueError("unknown unit")
    # TODO: add the "day" unit to the table
    return value * HOURS[unit]
