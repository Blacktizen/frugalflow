def parse_line(line):
    if not isinstance(line, str):
        raise ValueError("line must be a string")
    parts = [p.strip() for p in line.split(",")]
    if len(parts) not in (2, 3):
        raise ValueError("expected name,quantity[,unit]")
    name = parts[0]
    if name == "":
        raise ValueError("name must not be empty")
    try:
        qty = int(parts[1])
    except ValueError:
        raise ValueError("quantity must be an integer")
    if qty < 0:
        raise ValueError("quantity must not be negative")
    unit = parts[2] if len(parts) == 3 else ""
    if unit == "":
        unit = "pcs"
    return (name, qty, unit)
