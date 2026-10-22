def merge(left, right):
    result = dict(left)
    for name, qty in right.items():
        result[name] = result.get(name, 0) + qty
    return result
