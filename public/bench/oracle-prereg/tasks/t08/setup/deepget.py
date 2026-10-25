def deep_get(obj, path, default=None):
    if not path:
        return default
    segments = path.split('.')
    current = obj
    for seg in segments:
        bracket_start = seg.find('[')
        if bracket_start != -1:
            key_part = seg[:bracket_start]
            idx_part = seg[bracket_start + 1:seg.index(']')]
            if key_part:
                if isinstance(current, dict) and key_part in current:
                    current = current[key_part]
                else:
                    return default
            try:
                idx = int(idx_part)
            except ValueError:
                return default
            if isinstance(current, list):
                try:
                    current = current[idx]
                except IndexError:
                    return default
            else:
                return default
        else:
            if isinstance(current, dict) and seg in current:
                current = current[seg]
            else:
                return default
    if current is None:
        return default
    return current

