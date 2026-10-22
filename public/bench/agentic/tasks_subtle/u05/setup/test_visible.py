from intervals import merge

assert merge([[1, 3], [5, 7], [9, 11]]) == [[1, 3], [5, 7], [9, 11]]
assert merge([[1, 2], [3, 4]]) == [[1, 2], [3, 4]]
assert merge([[1, 5]]) == [[1, 5]]
assert merge([]) == []
