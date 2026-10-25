import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from luhn import luhn_valid

assert luhn_valid("4532015112830366") == True, "valid 16 digits no sep"
assert luhn_valid("123456789015") == True, "valid 12 digits no sep"
assert luhn_valid("1234 5678 9015") == True, "valid 12 digits with spaces"
assert luhn_valid("1234-5678-9015") == True, "valid 12 digits with dashes"

print("OK")
sys.exit(0)

