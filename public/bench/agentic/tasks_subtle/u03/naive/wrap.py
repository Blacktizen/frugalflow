def wrap(text, width):
    words = text.split()
    out = []
    line = ""
    for w in words:
        if not line:
            line = w
        elif len(line) + 1 + len(w) <= width:
            line += " " + w
        else:
            out.append(line)
            line = w
    if line or not words:
        out.append(line)
    return out
