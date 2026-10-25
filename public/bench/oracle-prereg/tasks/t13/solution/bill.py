def split_bill(total_cents, n):
    if n < 1:
        raise ValueError("n must be >= 1")
    if total_cents >= 0:
        q, r = divmod(total_cents, n)
        return [q + 1] * r + [q] * (n - r)
    else:
        q, r = divmod(-total_cents, n)
        return [-(q + 1)] * r + [-q] * (n - r)

