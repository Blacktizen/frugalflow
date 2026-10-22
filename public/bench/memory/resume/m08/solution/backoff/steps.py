def delay_at(base, factor, attempt):
    if not isinstance(attempt, int) or attempt < 0:
        raise ValueError("attempt must be a non-negative integer")
    return base * (factor ** attempt)
