MASS = {"kg": 1.0, "g": 0.001, "mg": 1e-6, "lb": 0.45359237}

def convert(value, from_unit, to_unit):
    if from_unit not in MASS or to_unit not in MASS:
        raise ValueError("unknown unit")
    return value * MASS[from_unit] / MASS[to_unit]
