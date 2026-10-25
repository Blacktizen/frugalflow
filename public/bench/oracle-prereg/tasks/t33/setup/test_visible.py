from hist import histogram

assert histogram([1, 3, 7], [0, 5, 10]) == [2, 1]
assert histogram([1, 20], [0, 5, 10]) == [1, 0]
assert histogram([], [0, 5, 10]) == [0, 0]
assert histogram([1, 2, 3], [0, 10]) == [3]

print("OK")

