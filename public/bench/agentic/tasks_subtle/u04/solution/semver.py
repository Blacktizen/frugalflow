def _split(v):
    core, _, _build = v.partition("+")
    head, _, pre = core.partition("-")
    core_parts = [int(x) for x in head.split(".") if x != ""]
    pre_parts = pre.split(".") if pre else []
    return core_parts, pre_parts


def compare(a, b):
    ac, ap = _split(a)
    bc, bp = _split(b)
    for i in range(max(len(ac), len(bc))):
        if i >= len(ac):
            return -1
        if i >= len(bc):
            return 1
        if ac[i] != bc[i]:
            return -1 if ac[i] < bc[i] else 1
    if not ap and not bp:
        return 0
    if not ap:
        return 1
    if not bp:
        return -1
    for i in range(max(len(ap), len(bp))):
        if i >= len(ap):
            return -1
        if i >= len(bp):
            return 1
        x, y = ap[i], bp[i]
        xn, yn = x.isdigit(), y.isdigit()
        if xn and yn:
            xi, yi = int(x), int(y)
            if xi != yi:
                return -1 if xi < yi else 1
        elif xn:
            return -1
        elif yn:
            return 1
        else:
            if x != y:
                return -1 if x < y else 1
    return 0
