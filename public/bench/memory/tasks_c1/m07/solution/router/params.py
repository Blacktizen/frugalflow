from router import segments

def extract(pattern, path):
    p = segments.segments(pattern)
    s = segments.segments(path)
    if len(p) != len(s):
        return None
    result = {}
    for name, value in zip(p, s):
        if name.startswith(":"):
            result[name[1:]] = value
        elif name == "*":
            continue
        elif name != value:
            return None
    return result
