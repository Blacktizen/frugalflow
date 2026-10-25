def keep_last(rows, key):
    last_index = {}
    for i, row in enumerate(rows):
        if key in row:
            last_index[row[key]] = i
    result = []
    for i, row in enumerate(rows):
        if key not in row:
            result.append(row)
        elif last_index[row[key]] == i:
            result.append(row)
    return result

