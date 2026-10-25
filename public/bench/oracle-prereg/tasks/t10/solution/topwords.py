from collections import Counter

def top_n(words, n):
    if n <= 0:
        return []
    cleaned = []
    for w in words:
        stripped = w.strip()
        if stripped:
            cleaned.append(stripped.lower())
    freq = Counter(cleaned)
    items = list(freq.items())
    items.sort(key=lambda x: (-x[1], x[0]))
    if n >= len(items):
        return items
    return items[:n]


