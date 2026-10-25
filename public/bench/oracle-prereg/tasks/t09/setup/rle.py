def rle_decode(s):
    if not s:
        return ""
    result = []
    i = 0
    while i < len(s):
        count_str = ""
        while i < len(s) and s[i].isdigit():
            count_str += s[i]
            i += 1
        if not count_str:
            result.append(s[i])
            i += 1
            continue
        count = int(count_str)
        if i >= len(s):
            break
        symbol = s[i]
        i += 1
        result.append(symbol * count)
    return "".join(result)

