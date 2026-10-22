def render(entries):
    lines = []
    for date_text, desc, amount in sorted(entries, key=lambda e: (e[0], e[1])):
        lines.append("{} {} {}".format(date_text, desc, amount))
    return "\n".join(lines) + ("\n" if lines else "")
