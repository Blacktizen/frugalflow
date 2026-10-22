import unittest
from backoff import sums

class TestSums(unittest.TestCase):
    def test_total(self):
        self.assertEqual(sums.total([1, 2, 3]), 6)
    def test_empty(self):
        self.assertEqual(sums.total([]), 0.0)

if __name__ == "__main__":
    unittest.main()
