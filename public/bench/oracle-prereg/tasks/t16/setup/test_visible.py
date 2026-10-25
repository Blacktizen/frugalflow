import sys
sys.path.insert(0, ".")
from rangelist import parse_ranges

assert parse_ranges("1-3,5,7-9") == [1, 2, 3, 5, 7, 8, 9]
assert parse_ranges("") == []
assert parse_ranges("5") == [5]
assert parse_ranges("1-3,5,7-9") == sorted(set(parse_ranges("1-3,5,7-9")))

print("OK")
sys.exit(0)

