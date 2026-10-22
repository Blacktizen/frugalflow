import unittest
from ledger import filter

class TestFilter(unittest.TestCase):
    def test_by_date(self):
        entries = [("2026-10-22", "a", 1.0), ("2026-10-21", "b", 2.0)]
        self.assertEqual(filter.by_date(entries, "2026-10-22"), [("2026-10-22", "a", 1.0)])
    def test_no_match(self):
        self.assertEqual(filter.by_date([("2026-10-22", "a", 1.0)], "2026-10-21"), [])

if __name__ == "__main__":
    unittest.main()
