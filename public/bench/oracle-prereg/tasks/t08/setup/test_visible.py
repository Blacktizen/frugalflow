import sys
sys.path.insert(0, '.')
from deepget import deep_get

obj = {"a": {"b": [10, 20, 30]}}

assert deep_get(obj, "a.b[1]") == 20
assert deep_get(obj, "a.b[-1]") == 30
assert deep_get(obj, "a.b[5]", "miss") == "miss"
assert deep_get({"x": {"y": 1}}, "x.z", "nope") == "nope"

print("OK")
sys.exit(0)

