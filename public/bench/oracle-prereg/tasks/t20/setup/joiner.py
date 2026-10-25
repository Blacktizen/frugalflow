def human_join(items, conj="and"):
    if not items:
        return ""
    filtered = []
    for item in items:
        if item is None:
            continue
        s = str(item)
        if s == "":
            continue
        filtered.append(s.strip())
    n = len(filtered)
    if n == 0:
        return ""
    if n == 1:
        return filtered[0]
    if n == 2:
        return filtered[0] + " " + conj + " " + filtered[1]
    return ", ".join(filtered[:-1]) + " " + conj + " " + filtered[-1]

