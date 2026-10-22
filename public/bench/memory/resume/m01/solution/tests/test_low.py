import unittest
from stock import low

class TestLow(unittest.TestCase):
    def test_below(self):
        self.assertEqual(low.below({"a": 1, "b": 5, "c": 3}, 4), ["a", "c"])
    def test_empty(self):
        self.assertEqual(low.below({}, 0), [])
    def test_zero(self):
        self.assertEqual(low.below({"a": 0}, 1), ["a"])

if __name__ == "__main__":
    unittest.main()
