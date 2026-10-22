def with_defaults(cfg, defaults):
    result = dict(cfg)
    for key, value in defaults.items():
        if key not in result or result[key] is None:
            result[key] = value
    return result
