import re

def compare(a, b):
    m1 = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-([^+]*))?(?:\+.*)?$', a)
    m2 = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-([^+]*))?(?:\+.*)?$', b)
    if not m1 or not m2:
        raise ValueError("invalid semver")
    for i in range(3):
        v1 = int(m1.group(i + 1))
        v2 = int(m2.group(i + 1))
        if v1 < v2: return -1
        if v1 > v2: return 1
    p1 = m1.group(4)
    p2 = m2.group(4)
    if p1 is None and p2 is None:
        return 0
    if p1 is None:
        return 1
    if p2 is None:
        return -1
    la = p1.split('.')
    lb = p2.split('.')
    for i in range(min(len(la), len(lb))):
        if la[i] < lb[i]: return -1
        if la[i] > lb[i]: return 1
    return 0

