import sys
sys.path.insert(0, ".")
from joiner import human_join

assert human_join([]) == ""
assert human_join(["hello"]) == "hello"
assert human_join(["hello", "world"]) == "hello and world"
print("OK")
sys.exit(0)

