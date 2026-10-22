import unittest
from tok import count

class TestCount(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(count.frequencies(["a", "b", "a"]), {"a": 2, "b": 1})
    def test_empty(self):
        self.assertEqual(count.frequencies([]), {})

if __name__ == "__main__":
    unittest.main()
