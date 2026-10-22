import datetime

from dates import add_months

assert add_months(datetime.date(2026, 1, 15), 1) == datetime.date(2026, 2, 15)
assert add_months(datetime.date(2026, 11, 15), 3) == datetime.date(2027, 2, 15)
assert add_months(datetime.date(2026, 3, 15), -1) == datetime.date(2026, 2, 15)
assert add_months(datetime.date(2026, 1, 15), -1) == datetime.date(2025, 12, 15)
print("visible tests passed")
