from textutil import dedupe

assert dedupe(["apple", "banana", "apple"]) == ["apple", "banana"]
assert dedupe(["x", "y", "z"]) == ["x", "y", "z"]
assert dedupe([]) == []
assert dedupe(["a", "a", "a"]) == ["a"]
print("visible tests passed")
