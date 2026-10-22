_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_duration(text):
    """Parse a duration like '1h30m' or '90s' into seconds."""
    s = "".join(text.split())
    if not s:
        raise ValueError("empty duration")
    total = 0
    pos = 0
    while pos < len(s):
        start = pos
        while pos < len(s) and s[pos].isdigit():
            pos += 1
        if start == pos:
            raise ValueError("expected a number")
        amount = int(s[start:pos])
        if pos >= len(s):
            raise ValueError("bare number without a unit")
        unit = s[pos].lower()
        if unit not in _UNITS:
            raise ValueError("unknown unit")
        total += amount * _UNITS[unit]
        pos += 1
    return total
