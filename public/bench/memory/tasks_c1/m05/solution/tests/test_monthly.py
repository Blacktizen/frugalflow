import unittest
from ledger import monthly

class TestMonthly(unittest.TestCase):
    def test_by_month(self):
        entries = [("2026-10-22", "a", 1.0), ("2026-10-21", "b", 2.0), ("2026-11-01", "c", 3.0)]
        self.assertEqual(monthly.by_month(entries), {"2026-10": 3.0, "2026-11": 3.0})
    def test_empty(self):
        self.assertEqual(monthly.by_month([]), {})

if __name__ == "__main__":
    unittest.main()
