from intervals import merge_intervals

result = merge_intervals([(1, 4), (3, 6)])
assert result == [(1, 6)], f"Expected [(1, 6)], got {result}"

result = merge_intervals([])
assert result == [], f"Expected [], got {result}"

result = merge_intervals([(2, 5)])
assert result == [(2, 5)], f"Expected [(2, 5)], got {result}"

result = merge_intervals([(1, 3), (5, 8)])
assert result == [(1, 3), (5, 8)], f"Expected [(1, 3), (5, 8)], got {result}"

print("OK")

