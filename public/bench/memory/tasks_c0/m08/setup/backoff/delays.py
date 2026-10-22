def exponential(base, factor, n):
    if not isinstance(n, int) or n < 0:
        raise ValueError("n must be a non-negative integer")
    result = []
    value = base
    for _ in range(n):
        result.append(value)
        value = value * factor
    return result
