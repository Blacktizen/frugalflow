def render(totals):
    lines = []
    for name in sorted(totals):
        lines.append(name + ": " + str(totals[name]))
    return "\n".join(lines) + ("\n" if lines else "")
