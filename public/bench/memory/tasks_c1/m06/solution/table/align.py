def pad(cell, width, align):
    if align == "left":
        return cell.ljust(width)
    if align == "right":
        return cell.rjust(width)
    if align == "center":
        total = width - len(cell)
        left = total // 2
        return " " * left + cell + " " * (total - left)
    raise ValueError("unknown align")
