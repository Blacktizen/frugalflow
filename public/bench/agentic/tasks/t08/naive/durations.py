import re

_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_duration(text):
    """Parse a duration like '1h30m' or '90s' into seconds."""
    total = 0
    for amount, unit in re.findall(r"(\d+)([dhms])", text):
        total += int(amount) * _UNITS[unit]
    return total
