def roman_to_int(s):
    values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    if not s:
        raise ValueError("empty string")
    s = s.upper()
    for ch in s:
        if ch not in values:
            raise ValueError("invalid character")
    if 'IIII' in s or 'XXXX' in s or 'CCCC' in s or 'MMMM' in s:
        raise ValueError("too many repetitions")
    total = 0
    i = 0
    while i < len(s):
        val = values[s[i]]
        if i + 1 < len(s) and values[s[i + 1]] > val:
            total += values[s[i + 1]] - val
            i += 2
        else:
            total += val
            i += 1
    if total < 1 or total > 3999:
        raise ValueError("out of range")
    return total

