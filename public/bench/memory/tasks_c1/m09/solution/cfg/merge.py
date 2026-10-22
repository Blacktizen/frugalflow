def merge(base, overrides):
    result = dict(base)
    for key, value in overrides.items():
        if value is not None:
            result[key] = value
    return result
