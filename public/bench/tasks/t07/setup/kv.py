def parse_key_values(text):
    result = {}
    for line in text.splitlines():
        if not line or line[0] == "#":
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result
