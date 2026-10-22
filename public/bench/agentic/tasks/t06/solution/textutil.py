import unicodedata


def dedupe(items):
    """Return unique strings keeping first-occurrence order."""
    seen = set()
    out = []
    for item in items:
        key = unicodedata.normalize("NFC", item.strip()).casefold()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
