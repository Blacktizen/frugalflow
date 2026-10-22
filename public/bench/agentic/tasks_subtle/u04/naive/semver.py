def compare(a, b):
    a = a.split("+")[0]
    b = b.split("+")[0]

    def nums(s):
        return [int(x) for x in s.split("-")[0].split(".")]

    na, nb = nums(a), nums(b)
    while len(na) < 3:
        na.append(0)
    while len(nb) < 3:
        nb.append(0)
    na, nb = na[:3], nb[:3]
    if na != nb:
        return -1 if na < nb else 1
    ra = a.split("-", 1)[1] if "-" in a else None
    rb = b.split("-", 1)[1] if "-" in b else None
    if ra is None and rb is None:
        return 0
    if ra is None:
        return 1
    if rb is None:
        return -1
    return -1 if ra < rb else 1
