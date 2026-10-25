import sys
from brackets import balanced

cases = [
    ("()", True),
    ("([{}])", True),
    ("(()", False),
    ("'('", True),
]

for inp, exp in cases:
    got = balanced(inp)
    if got != exp:
        sys.exit(1)

print("OK")
sys.exit(0)

