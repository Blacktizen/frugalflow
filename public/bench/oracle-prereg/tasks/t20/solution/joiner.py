def human_join(items, conj="and"):
    filtered = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, str) and item.strip() == "":
            continue
        filtered.append(str(item).strip())
    n = len(filtered)
    if n == 0:
        return ""
    if n == 1:
        return filtered[0]
    if n == 2:
        return filtered[0] + " " + conj + " " + filtered[1]
    return ", ".join(filtered[:-1]) + ", " + conj + " " + filtered[-1]

