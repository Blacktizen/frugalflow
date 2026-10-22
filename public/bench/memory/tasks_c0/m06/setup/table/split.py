def split(text):
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    rows = []
    for line in text.split("\n"):
        if line.strip() == "":
            continue
        cells = line.split("|")
        if line.startswith("|"):
            cells = cells[1:]
        if line.endswith("|"):
            cells = cells[:-1]
        rows.append([c.strip() for c in cells])
    return rows
