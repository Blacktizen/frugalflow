def parse_key_values(text):
    result = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def to_csv_row(fields):
    out = []
    for field in fields:
        if any(ch in field for ch in ',"\n'):
            field = '"' + field.replace('"', '""') + '"'
        out.append(field)
    return ",".join(out)


def parse_numbers(text):
    result = []
    for token in text.split():
        try:
            result.append(int(token))
        except ValueError:
            raise ValueError("not an integer: " + token)
    return result
