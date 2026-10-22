import unittest
from ledger import order

class TestOrder(unittest.TestCase):
    def test_tie_break(self):
        entries = [("2026-10-22", "b", 1.0), ("2026-10-22", "a", 2.0), ("2026-10-21", "c", 3.0)]
        self.assertEqual(order.sorted_entries(entries), [("2026-10-21", "c", 3.0), ("2026-10-22", "a", 2.0), ("2026-10-22", "b", 1.0)])
    def test_does_not_mutate(self):
        entries = [("2026-10-22", "b", 1.0), ("2026-10-22", "a", 2.0)]
        order.sorted_entries(entries)
        self.assertEqual(entries, [("2026-10-22", "b", 1.0), ("2026-10-22", "a", 2.0)])

if __name__ == "__main__":
    unittest.main()
