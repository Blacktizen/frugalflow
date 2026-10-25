import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boolparse import parse_bool

assert parse_bool(True) is True
assert parse_bool(1) is True
assert parse_bool(0) is False
assert parse_bool("yes") is True
print("OK")
sys.exit(0)

