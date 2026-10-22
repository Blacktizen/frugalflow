from cfg import merge

assert merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
assert merge({"a": 1}, {"a": 3}) == {"a": 3}
assert merge({}, {"a": 1}) == {"a": 1}
assert merge({"a": 1}, {}) == {"a": 1}
print("visible tests passed")
