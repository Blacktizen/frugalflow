def to_int(value, default, lo, hi):
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("bool is not an int")
    try:
        n = int(value)
    except (ValueError, TypeError):
        raise ValueError("not an integer")
    if n < lo or n > hi:
        raise ValueError("out of range")
    return n
