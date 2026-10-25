def rle_decode(s):
    if not s:
        return ""
    if not s[0].isdigit():
        raise ValueError("Invalid RLE string: starts with non-digit")
    result = []
    i = 0
    n = len(s)
    while i < n:
        if not s[i].isdigit():
            raise ValueError("Invalid RLE string: symbol without count")
        count_str = ""
        while i < n and s[i].isdigit():
            count_str += s[i]
            i += 1
        count = int(count_str)
        if i >= n:
            raise ValueError("Invalid RLE string: ends with digits without symbol")
        symbol = s[i]
        i += 1
        if count > 0:
            result.append(symbol * count)
    return "".join(result)

