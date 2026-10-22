def widths(rows):
    if not rows:
        return []
    n = max(len(r) for r in rows)
    result = [0] * n
    for r in rows:
        for i in range(n):
            cell = r[i] if i < len(r) else ""
            result[i] = max(result[i], len(cell))
    return result
