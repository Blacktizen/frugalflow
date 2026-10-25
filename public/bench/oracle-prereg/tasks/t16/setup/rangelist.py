def parse_ranges(s):
    stripped = s.strip()
    if not stripped:
        return []
    parts = stripped.split(",")
    result = set()
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            segs = part.split("-")
            if len(segs) != 2:
                raise ValueError("invalid range")
            try:
                a = int(segs[0])
                b = int(segs[1])
            except ValueError:
                raise ValueError("non-numeric or negative")
            if a > b:
                a, b = b, a
            for v in range(a, b + 1):
                result.add(v)
        else:
            try:
                result.add(int(part))
            except ValueError:
                raise ValueError("non-numeric or negative")
    return sorted(result)

