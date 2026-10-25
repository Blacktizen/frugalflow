import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flat import flatten

assert flatten({"a": {"b": 1}}) == {"a.b": 1}
assert flatten({"a": [10, 20]}) == {"a.0": 10, "a.1": 20}
assert flatten({1: "x"}) == {"1": "x"}
assert flatten({"a": {"b": {"c": 2}}}) == {"a.b.c": 2}

print("OK")
sys.exit(0)

