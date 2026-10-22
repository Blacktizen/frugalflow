def by_month(entries):
    result = {}
    for date_text, desc, amount in entries:
        key = date_text[:7]
        result[key] = result.get(key, 0.0) + amount
    return result
