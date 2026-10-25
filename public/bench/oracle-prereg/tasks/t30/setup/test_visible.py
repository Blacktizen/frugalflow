import sys
sys.path.insert(0, ".")
from batching import batch_by_weight

assert batch_by_weight([("A", 2), ("B", 3), ("C", 4)], 6) == [["A", "B"], ["C"]]
assert batch_by_weight([("A", 10)], 5) == [["A"]]
assert batch_by_weight([], 3) == []
assert batch_by_weight([("A", 1), ("B", 1), ("C", 1)], 10) == [["A", "B", "C"]]
print("OK")
sys.exit(0)

