def to_csv_row(fields):
    out = []
    for field in fields:
        if any(ch in field for ch in ',"\n'):
            field = '"' + field.replace('"', '""') + '"'
        out.append(field)
    return ",".join(out)
