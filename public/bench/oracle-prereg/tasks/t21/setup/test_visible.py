from compress import ranges_from_ints
assert ranges_from_ints([1, 2, 3, 5]) == "1-3,5"
assert ranges_from_ints([]) == ""
assert ranges_from_ints([7, 7, 8, 9, 10, 11]) == "7-11"
print("OK")
import sys
sys.exit(0)

