def total(lines):
    t = 0.0
    for price, qty, tax in lines:
        t += float(price) * qty * (1 + tax / 100)
    return int(round(t * 100))
