def split_bill(total_cents, n):
    if n == 0:
        raise ValueError("n must be >= 1")
    q = total_cents // n
    r = total_cents % n
    return [q + 1] * r + [q] * (n - r)

