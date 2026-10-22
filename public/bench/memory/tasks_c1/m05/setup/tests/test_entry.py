import unittest
from ledger import entry

class TestEntry(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(entry.parse("2026-10-22 coffee 1.50"), ("2026-10-22", "coffee", 1.5))
    def test_spaces(self):
        self.assertEqual(entry.parse("2026-10-22 coffee beans -5.25"), ("2026-10-22", "coffee beans", -5.25))
    def test_zero(self):
        self.assertEqual(entry.parse("2026-10-22 x 0"), ("2026-10-22", "x", 0.0))
    def test_errors(self):
        for bad in ["2026-13-01 x 1", "2026-10-32 x 1", "bad x 1", "2026-10-22  1", "2026-10-22 x abc"]:
            with self.assertRaises(ValueError):
                entry.parse(bad)

if __name__ == "__main__":
    unittest.main()
