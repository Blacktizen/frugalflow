from ragged import transpose_ragged

assert transpose_ragged([]) == []

r = transpose_ragged([[1, 2, 3], [4, 5, 6]])
assert list(r[0]) == [1, 4]
assert list(r[1]) == [2, 5]
assert list(r[2]) == [3, 6]

r2 = transpose_ragged([[1, 2], [3, 4, 5]])
assert len(r2) == 3
assert list(r2[0]) == [1, 3]
assert list(r2[1]) == [2, 4]
assert list(r2[2]) == [None, 5]

print("OK")

