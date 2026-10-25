def roman_to_int(s):
    if not s:
        raise ValueError("empty string")
    valid_chars = set("IVXLCDM")
    for ch in s:
        if ch not in valid_chars:
            raise ValueError("invalid character: must be uppercase I, V, X, L, C, D, M")
    values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    total = 0
    for i in range(len(s)):
        val = values[s[i]]
        if i + 1 < len(s) and values[s[i + 1]] > val:
            total -= val
        else:
            total += val
    if total < 1 or total > 3999:
        raise ValueError("out of range: value must be 1 to 3999")
    canon = _int_to_roman(total)
    if canon != s:
        raise ValueError("non-canonical Roman numeral")
    return total


def _int_to_roman(n):
    table = [
        (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
        (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
        (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')
    ]
    out = []
    for val, sym in table:
        while n >= val:
            out.append(sym)
            n -= val
    return ''.join(out)

