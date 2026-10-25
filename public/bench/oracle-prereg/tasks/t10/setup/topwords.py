from collections import Counter

def top_n(words, n):
    if n is None:
        n = 0
    cleaned = [w.lower() for w in words]
    freq = Counter(cleaned)
    items = list(freq.items())
    items.sort(key=lambda x: (-x[1], x[0]))
    if n >= len(items):
        return items
    return items[:n]


