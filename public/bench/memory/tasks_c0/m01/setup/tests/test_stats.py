import unittest
from stock import stats

class TestStats(unittest.TestCase):
    def test_sums(self):
        self.assertEqual(stats.total([("a", 2, "kg"), ("a", 3, "kg"), ("b", 1, "pcs")]), {"a": 5, "b": 1})
    def test_empty(self):
        self.assertEqual(stats.total([]), {})

if __name__ == "__main__":
    unittest.main()
