def total(parsed):
    result = {}
    for name, qty, unit in parsed:
        result[name] = result.get(name, 0) + qty
    return result
