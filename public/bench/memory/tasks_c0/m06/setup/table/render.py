from table import widths as _widths

def render(rows):
    if not rows:
        return ""
    w = _widths.widths(rows)
    n = len(w)
    def line(cells):
        out = []
        for i in range(n):
            cell = cells[i] if i < len(cells) else ""
            out.append(cell.ljust(w[i]))
        return "| " + " | ".join(out) + " |"
    result = [line(rows[0])]
    result.append("| " + " | ".join("-" * w[i] for i in range(n)) + " |")
    for r in rows[1:]:
        result.append(line(r))
    return "\n".join(result) + "\n"
