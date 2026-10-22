from router import segments

def match(pattern, path):
    p = segments.segments(pattern)
    s = segments.segments(path)
    if len(p) != len(s):
        return False
    for a, b in zip(p, s):
        if a != "*" and a != b:
            return False
    return True
