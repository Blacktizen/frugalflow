def ranges_from_ints(nums):
    if not nums:
        return ""
    sorted_nums = sorted(set(nums))
    groups = []
    current = [sorted_nums[0]]
    for n in sorted_nums[1:]:
        if n == current[-1] + 1:
            current.append(n)
        else:
            groups.append(current)
            current = [n]
    groups.append(current)
    parts = []
    for g in groups:
        if len(g) >= 3:
            parts.append(str(g[0]) + "-" + str(g[-1]))
        elif len(g) == 2:
            parts.append(str(g[0]) + "," + str(g[1]))
        else:
            parts.append(str(g[0]))
    return ",".join(parts)

