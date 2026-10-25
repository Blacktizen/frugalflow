def luhn_valid(s):
    if not isinstance(s, str):
        return False
    try:
        cleaned = []
        for c in s:
            if c == ' ' or c == '-':
                continue
            if c.isdigit():
                cleaned.append(c)
            else:
                return False
        if len(cleaned) < 12 or len(cleaned) > 19:
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
    except Exception:
        return False

