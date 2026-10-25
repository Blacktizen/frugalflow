def luhn_valid(s):
    if not isinstance(s, str):
        return False
    cleaned = ''.join(c for c in s if c.isdigit())
    if len(cleaned) == 0:
        return False
    digits = [int(c) for c in cleaned]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d = d * 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0

