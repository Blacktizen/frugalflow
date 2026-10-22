import re

def parse(line):
    if not isinstance(line, str):
        raise ValueError("line must be a string")
    parts = line.split(" ", 1)
    if len(parts) != 2:
        raise ValueError("expected 'YYYY-MM-DD description amount'")
    date_text, rest = parts
    rest_parts = rest.rsplit(" ", 1)
    if len(rest_parts) != 2:
        raise ValueError("expected 'YYYY-MM-DD description amount'")
    desc, amount_text = rest_parts
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        raise ValueError("bad date")
    month = int(date_text[5:7])
    day = int(date_text[8:10])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError("bad date")
    if desc.strip() == "":
        raise ValueError("description must not be empty")
    try:
        amount = float(amount_text)
    except ValueError:
        raise ValueError("amount must be a number")
    return (date_text, desc, amount)
