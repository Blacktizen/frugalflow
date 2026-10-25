def transpose_ragged(rows, fill=None):
    if not rows:
        return []
    max_len = max(len(r) for r in rows)
    result = []
    for j in range(max_len):
        col = tuple(row[j] if j < len(row) else fill for row in rows)
        result.append(col)
    for r in rows:
        while len(r) < max_len:
            r.append(fill)
    return result

