import re

def compare(a, b):
    def parse(v):
        m = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-([^+]*))?(?:\+.*)?$', v)
        if not m:
            raise ValueError("invalid semver: " + v)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4))

    def cmp_ident(x, y):
        xn = x.isdigit()
        yn = y.isdigit()
        if xn and yn:
            ix, iy = int(x), int(y)
            if ix < iy: return -1
            if ix > iy: return 1
            return 0
        if xn and not yn:
            return -1
        if not xn and yn:
            return 1
        if x < y: return -1
        if x > y: return 1
        return 0

    def cmp_pre(pa, pb):
        if pa is None and pb is None:
            return 0
        if pa is None:
            return 1
        if pb is None:
            return -1
        la = pa.split('.')
        lb = pb.split('.')
        for i in range(min(len(la), len(lb))):
            c = cmp_ident(la[i], lb[i])
            if c != 0:
                return c
        if len(la) < len(lb):
            return -1
        if len(la) > len(lb):
            return 1
        return 0

    a1, a2, a3, ap = parse(a)
    b1, b2, b3, bp = parse(b)

    if a1 != b1: return -1 if a1 < b1 else 1
    if a2 != b2: return -1 if a2 < b2 else 1
    if a3 != b3: return -1 if a3 < b3 else 1

    return cmp_pre(ap, bp)

