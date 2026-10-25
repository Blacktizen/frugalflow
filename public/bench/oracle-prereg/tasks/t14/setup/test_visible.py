import sys

from pct import pct_change

try:
    assert pct_change(100, 110) == 10.0
    assert pct_change(200, 180) == -10.0
    assert pct_change(0, 5) is None
    assert pct_change(50, 60) == 20.0
    print("OK")
    sys.exit(0)
except AssertionError:
    sys.exit(1)

