from movavg import moving_average

assert moving_average([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]
assert moving_average([1, 2, 3, 4], 5) == []
assert moving_average([10, 20, 30], 3) == [20.0]
assert moving_average([5], 1) == [5.0]
print("OK")

