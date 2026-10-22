def pad(cell, width, align):
    if align == "left":
        return cell.ljust(width)
    if align == "right":
        return cell.rjust(width)
    # TODO: implement center alignment
    raise ValueError("unknown align")
