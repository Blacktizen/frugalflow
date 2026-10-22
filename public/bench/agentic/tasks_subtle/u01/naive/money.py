def parse_amount(text):
    s = text.strip()
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    elif s.startswith("-"):
        negative = True
        s = s[1:].strip()
    for sym in ("$", "€", "£"):
        s = s.replace(sym, "")
    s = s.replace("EUR", "").replace("USD", "").strip()
    if s.count(".") > 1 or s.count(",") > 1:
        raise ValueError("bad amount")
    s = s.replace(",", "")
    if not s or not all(c.isdigit() or c == "." for c in s):
        raise ValueError("bad amount")
    cents = int(round(float(s) * 100))
    return -cents if negative else cents
