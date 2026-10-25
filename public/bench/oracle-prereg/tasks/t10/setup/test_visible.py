import sys
from topwords import top_n

# Basic frequency and ordering
assert top_n(["apple", "banana", "apple", "cherry"], 2) == [("apple", 2), ("banana", 1)]

# Case insensitive, lowercase output
assert top_n(["Apple", "apple", "BANANA"], 2) == [("apple", 2), ("banana", 1)]

# Alphabetical tie-break
assert top_n(["zebra", "alpha", "beta", "alpha", "beta"], 3) == [("alpha", 2), ("beta", 2), ("zebra", 1)]

print("OK")
sys.exit(0)


