def parse_ranges(s):
    stripped = s.strip()
    if not stripped:
        return []
    parts = stripped.split(",")
    for part in parts:
        if part.strip() == "":
            raise ValueError("empty element")
    result = set()
    for part in parts:
        token = part.strip()
        if "-" in token:
            segs = token.split("-")
            if len(segs) != 2:
                raise ValueError("invalid range")
            left, right = segs[0], segs[1]
            if left == "" or right == "":
                raise ValueError("invalid range")
            for seg in (left, right):
                if not seg.isdigit():
                    raise ValueError("non-numeric or negative character")
            a = int(left)
            b = int(right)
            if a > b:
                raise ValueError("inverse range")
            for v in range(a, b + 1):
                result.add(v)
        else:
            if not token.isdigit():
                raise ValueError("non-numeric or negative character")
            result.add(int(token))
    return sorted(result)

