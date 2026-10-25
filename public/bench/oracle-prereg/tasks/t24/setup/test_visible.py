import sys
from sortedins import insert_sorted

try:
    assert insert_sorted([1, 3, 5], 4) == [1, 3, 4, 5]
    assert insert_sorted([2, 4], 1) == [1, 2, 4]
    assert insert_sorted([1, 3], 5) == [1, 3, 5]
    assert insert_sorted([10, 20], 15, key=lambda v: v) == [10, 15, 20]
except AssertionError:
    sys.exit(1)

print("OK")
sys.exit(0)

