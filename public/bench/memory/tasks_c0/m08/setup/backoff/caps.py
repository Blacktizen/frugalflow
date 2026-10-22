def cap(delay, maximum):
    if maximum < 0:
        raise ValueError("maximum must not be negative")
    return min(delay, maximum)
