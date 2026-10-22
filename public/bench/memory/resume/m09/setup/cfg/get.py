def get(cfg, key, default=None):
    value = cfg.get(key)
    if value is None:
        return default
    return value
