def dedupe(items):
    """Return unique strings keeping first-occurrence order."""
    seen = set()
    out = []
    for item in items:
        key = item.strip().lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
