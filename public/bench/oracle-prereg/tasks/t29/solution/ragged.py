def transpose_ragged(rows, fill=None):
    if not rows:
        return []
    max_len = max(len(r) for r in rows)
    if max_len == 0:
        return []
    result = []
    for j in range(max_len):
        col = [row[j] if j < len(row) else fill for row in rows]
        result.append(col)
    return result

