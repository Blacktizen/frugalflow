def merge(base, override):
    """Return a new dict deep-merging override into base."""
    result = base
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            merge(result[key], value)
        else:
            result[key] = value
    return result
