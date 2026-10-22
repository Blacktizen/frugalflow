LENGTH = {"m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "mi": 1609.344}

def convert(value, from_unit, to_unit):
    if from_unit not in LENGTH or to_unit not in LENGTH:
        raise ValueError("unknown unit")
    return value * LENGTH[from_unit] / LENGTH[to_unit]
