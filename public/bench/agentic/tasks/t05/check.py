import datetime
import sys

from dates import add_months

cases = [
    ("Jan 31 +1 non-leap", datetime.date(2026, 1, 31), 1, datetime.date(2026, 2, 28)),
    ("Jan 31 +1 leap", datetime.date(2024, 1, 31), 1, datetime.date(2024, 2, 29)),
    ("Mar 31 -1", datetime.date(2026, 3, 31), -1, datetime.date(2026, 2, 28)),
    ("May 31 -1", datetime.date(2026, 5, 31), -1, datetime.date(2026, 4, 30)),
    ("Aug 31 +1", datetime.date(2026, 8, 31), 1, datetime.date(2026, 9, 30)),
    ("Dec 31 +1", datetime.date(2025, 12, 31), 1, datetime.date(2026, 1, 31)),
    ("negative crossing years", datetime.date(2026, 1, 15), -13, datetime.date(2024, 12, 15)),
    ("Oct 31 +4", datetime.date(2026, 10, 31), 4, datetime.date(2027, 2, 28)),
    ("mid-month -1", datetime.date(2026, 3, 15), -1, datetime.date(2026, 2, 15)),
    ("zero months", datetime.date(2026, 3, 31), 0, datetime.date(2026, 3, 31)),
]

for label, d, n, expected in cases:
    try:
        got = add_months(d, n)
    except Exception as e:
        print("FAIL", label, "raised", type(e).__name__, str(e))
        sys.exit(1)
    if got != expected:
        print("FAIL", label, "got", got, "expected", expected)
        sys.exit(1)

print("PASS")
