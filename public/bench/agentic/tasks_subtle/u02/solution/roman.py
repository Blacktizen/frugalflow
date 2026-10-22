_VALS = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
          (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
          (5, "V"), (4, "IV"), (1, "I")]
_MAP = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def to_roman(n):
    if not isinstance(n, int) or not 1 <= n <= 3999:
        raise ValueError("out of range")
    out = []
    for v, s in _VALS:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


def _value(s):
    s = s.upper()
    total = 0
    for i, ch in enumerate(s):
        if ch not in _MAP:
            raise ValueError("bad numeral")
        v = _MAP[ch]
        if i + 1 < len(s) and _MAP[s[i + 1]] > v:
            total -= v
        else:
            total += v
    return total


def from_roman(s):
    if not s or s.strip() != s:
        raise ValueError("bad numeral")
    v = _value(s)
    if to_roman(v) != s.upper():
        raise ValueError("not canonical")
    return v
