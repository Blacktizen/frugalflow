from chunks import windows

assert windows([1,2,3,4,5,6], 3, 1) == [[1,2,3],[3,4,5],[5,6]]
assert windows([], 3, 0) == []
assert windows([1,2,3,4], 2, 0) == [[1,2],[3,4]]
try:
    windows([1,2,3], 0)
    exit(1)
except ValueError:
    pass

print("OK")

