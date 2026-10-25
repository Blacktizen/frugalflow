def keep_last(rows, key):
    seen = set()
    result = []
    for row in rows:
        if key not in row:
            continue
        val = row[key]
        if val in seen:
            continue
        seen.add(val)
        result.append(row)
    return result

